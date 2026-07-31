"""告警引擎:多源拉取 → 按类别评估 → 触发通知。

- price:穿越检测(仅"未满足→满足"触发)+ cooldown 冷却,防震荡轰炸
- whale:按资产/金额过滤,key 跨轮去重 + cooldown 节流
- rss:按 feed URL 匹配,可选关键词过滤,key 跨轮去重 + cooldown 节流
"""
import logging
import time

from db import DB
from notify import send_alert
from sources.base import AlertItem, Source

logger = logging.getLogger(__name__)

# 去重集合大小上限,超过后裁剪,防长期运行内存膨胀
SEEN_CAP = 5000
SEEN_TRIM = 2000


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


def _rss_text(sub: dict, item: AlertItem) -> str:
    ext = item.extra
    title = ext.get("title") or "(无标题)"
    link = ext.get("link") or ""
    summary = (ext.get("summary") or "").replace("\n", " ")
    if len(summary) > 120:
        summary = summary[:117] + "…"
    kw = f" · 关键词: {sub['filter']}" if sub.get("filter") else ""
    return f"📰 {title}\n{link}\n{summary}\n(订阅 #{sub['id']}{kw})"


class Engine:
    def __init__(self, db: DB, sources: dict[str, Source], cooldown: int = 1800):
        self.db = db
        self.sources = sources
        self.cooldown = cooldown
        # sub_id -> {"satisfied": bool, "last_fire": float}
        self._state: dict[int, dict] = {}
        # category -> 已处理 key 集合(跨轮去重)
        self._seen: dict[str, set[str]] = {}

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
            elif sub["category"] == "rss":
                fired += await self._eval_rss(sub, items.get("rss", []))
        # 标记本轮已处理的 key(下轮跳过);本轮内所有订阅共享判定
        for cat in ("whale", "rss"):
            for it in items.get(cat, []):
                self._mark_seen(cat, it.key)
        logger.info("tick: 订阅=%d 触发=%d", len(self.db.list_subscriptions()), fired)
        return fired

    # ---------- 内部 ----------
    async def _fetch_all(self) -> dict[str, list[AlertItem]]:
        result: dict[str, list[AlertItem]] = {}
        for cat, src in self.sources.items():
            try:
                result[cat] = await src.fetch()
            except Exception as exc:
                logger.warning("源 %s 拉取失败: %s", cat, exc)
                result[cat] = []
        return result

    def _mark_seen(self, cat: str, key: str) -> None:
        s = self._seen.setdefault(cat, set())
        s.add(key)
        if len(s) > SEEN_CAP:
            self._seen[cat] = set(list(s)[-SEEN_TRIM:])

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
        seen = self._seen.get("whale", set())
        for it in items:
            if it.key in seen:
                continue  # 已在上轮处理过
            if sub["asset"] != "ANY" and it.asset != sub["asset"]:
                continue
            if it.value < sub["threshold"]:
                continue
            if (now - st["last_fire"]) < self.cooldown:
                continue  # 节流
            st["last_fire"] = now
            await send_alert(sub["user_id"], sub["id"], _whale_text(sub, it))
            fired += 1
        return fired

    async def _eval_rss(self, sub: dict, items: list[AlertItem]) -> int:
        st = self._state.setdefault(sub["id"], {"satisfied": False, "last_fire": 0.0})
        now = time.time()
        keywords = [k.strip().lower() for k in (sub.get("filter") or "").split(",") if k.strip()]
        fired = 0
        seen = self._seen.get("rss", set())
        for it in items:
            if it.asset != sub["asset"]:
                continue
            if it.key in seen:
                continue
            if keywords:
                blob = f"{it.extra.get('title', '')} {it.extra.get('summary', '')}".lower()
                if not any(k in blob for k in keywords):
                    continue
            if (now - st["last_fire"]) < self.cooldown:
                continue  # 节流
            st["last_fire"] = now
            await send_alert(sub["user_id"], sub["id"], _rss_text(sub, it))
            fired += 1
        return fired
