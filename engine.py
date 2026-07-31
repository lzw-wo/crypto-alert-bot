"""告警引擎:多源拉取 → 按类别评估 → 触发通知。

- price:穿越检测(仅"未满足→满足"触发)+ cooldown 冷却,防震荡轰炸
- whale:按资产/金额过滤,交易 hash 去重(源层),cooldown 节流
"""
import logging
import time

from db import DB
from notify import send_alert
from sources.base import AlertItem, Source

logger = logging.getLogger(__name__)


def _price_text(sub: dict, item: AlertItem) -> str:
    op_cn = "高于" if sub["op"] == "gt" else "低于"
    arrow = "🚀 突破" if sub["op"] == "gt" else "📉 跌破"
    return (
        f"{arrow} {sub['asset']} {op_cn} ${sub['threshold']:,.2f}\n"
        f"当前价格 ${item.value:,.2f}\n"
        f"(订阅 #{sub['id']})"
    )


def _whale_text(sub: dict, item: AlertItem) -> str:
    ext = item.extra
    scope = "全部币种" if sub["asset"] == "ANY" else sub["asset"]
    return (
        f"🐋 巨鲸转账 {item.asset} ${item.value:,.0f}\n"
        f"链: {ext.get('blockchain', '?')} | 数量: {ext.get('amount', '?')} {item.asset}\n"
        f"{ext.get('from', '?')} → {ext.get('to', '?')}\n"
        f"(订阅 #{sub['id']} · 范围 {scope})"
    )


class Engine:
    def __init__(self, db: DB, sources: dict[str, Source], cooldown: int = 1800):
        self.db = db
        self.sources = sources
        self.cooldown = cooldown
        # sub_id -> {"satisfied": bool, "last_fire": float}
        self._state: dict[int, dict] = {}
        # 引擎级巨鲸去重(源层已去重,此处为双保险)
        self._seen_whale: set[str] = set()

    def seed_state(self):
        for sub in self.db.list_subscriptions():
            self._state.setdefault(sub["id"], {"satisfied": False, "last_fire": 0.0})

    async def tick(self) -> int:
        items = await self._fetch_all()
        fired = 0
        for sub in self.db.list_subscriptions():
            if sub["category"] == "price":
                fired += await self._eval_price(sub, items.get("price", []))
            elif sub["category"] == "whale":
                fired += await self._eval_whale(sub, items.get("whale", []))
        # 标记本轮已处理的 whale key(下轮跳过);本轮内所有订阅共享判定
        for it in items.get("whale", []):
            self._seen_whale.add(it.key)
            if len(self._seen_whale) > 5000:
                self._seen_whale = set(list(self._seen_whale)[-2000:])
        logger.info("tick: 订阅=%d 触发=%d", len(self.db.list_subscriptions()), fired)
        return fired

    async def _fetch_all(self) -> dict[str, list[AlertItem]]:
        result: dict[str, list[AlertItem]] = {}
        for cat, src in self.sources.items():
            try:
                result[cat] = await src.fetch()
            except Exception as exc:
                logger.warning("源 %s 拉取失败: %s", cat, exc)
                result[cat] = []
        return result

    async def _eval_price(self, sub: dict, items: list[AlertItem]) -> int:
        matches = [it for it in items if it.asset == sub["asset"]]
        if not matches:
            return 0
        item = matches[0]
        st = self._state.setdefault(sub["id"], {"satisfied": False, "last_fire": 0.0})
        now = time.time()
        satisfied = item.value >= sub["threshold"] if sub["op"] == "gt" else item.value <= sub["threshold"]
        if satisfied and not st["satisfied"] and (now - st["last_fire"]) >= self.cooldown:
            st["satisfied"] = True
            st["last_fire"] = now
            await send_alert(sub["user_id"], sub["id"], _price_text(sub, item))
            return 1
        if not satisfied:
            st["satisfied"] = False
        return 0

    async def _eval_whale(self, sub: dict, items: list[AlertItem]) -> int:
        st = self._state.setdefault(sub["id"], {"satisfied": False, "last_fire": 0.0})
        now = time.time()
        fired = 0
        for it in items:
            if it.key in self._seen_whale:
                continue  # 已在上轮处理过
            if sub["asset"] != "ANY" and it.asset != sub["asset"]:
                continue
            if it.value < sub["threshold"]:
                continue
            if (now - st["last_fire"]) < self.cooldown:
                continue  # 节流:距上次推送不足冷却期
            st["last_fire"] = now
            await send_alert(sub["user_id"], sub["id"], _whale_text(sub, it))
            fired += 1
        return fired
