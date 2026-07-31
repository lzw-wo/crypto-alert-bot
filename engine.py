"""告警引擎:轮询 → 穿越检测 → 冷却 → 触发通知。

穿越检测:仅当"上一轮未满足条件 → 本轮满足"时触发,避免每轮都轰炸;
触发后进入 cooldown 冷却,价格回落撤销条件后重新"上膛"。
"""
import logging
import time

from db import DB
from notify import notify
from sources.base import Source

logger = logging.getLogger(__name__)


class Engine:
    def __init__(self, db: DB, source: Source, cooldown: int = 1800):
        self.db = db
        self.source = source
        self.cooldown = cooldown
        # sub_id -> {"satisfied": bool, "last_fire": float}
        self._state: dict[int, dict] = {}

    def seed_state(self):
        """启动时按当前订阅重建状态(全部置为未满足,等待首穿触发)。"""
        for sub in self.db.list_subscriptions():
            self._state.setdefault(sub["id"], {"satisfied": False, "last_fire": 0.0})

    async def tick(self) -> int:
        """一次轮询。返回本轮触发条数。"""
        try:
            points = await self.source.fetch()
        except Exception as exc:
            logger.warning("拉取行情失败: %s", exc)
            return 0
        prices = {p.asset: p.price for p in points}

        now = time.time()
        fired = 0
        for sub in self.db.list_subscriptions():
            price = prices.get(sub["asset"])
            if price is None:
                continue
            st = self._state.setdefault(sub["id"], {"satisfied": False, "last_fire": 0.0})
            satisfied = price >= sub["threshold"] if sub["op"] == "gt" else price <= sub["threshold"]

            if satisfied and not st["satisfied"] and (now - st["last_fire"]) >= self.cooldown:
                st["satisfied"] = True
                st["last_fire"] = now
                await notify(sub, price)
                fired += 1
            elif not satisfied:
                st["satisfied"] = False

        logger.info("tick: 订阅=%d 触发=%d", len(self.db.list_subscriptions()), fired)
        return fired
