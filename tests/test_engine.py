"""断言测试:穿越检测 / 去重 / 回落重置 / 冷却。用假数据源,不联网。

运行:PYTHONPATH=. .venv/Scripts/python tests/test_engine.py
"""
import asyncio
import os
import tempfile

os.environ["DRY_RUN"] = "1"
os.environ["DB_PATH"] = os.path.join(tempfile.gettempdir(), "test_engine.db")
os.environ["LOG_FILE"] = os.path.join(tempfile.gettempdir(), "test_alerts.log")

import config  # noqa: E402
from db import DB  # noqa: E402
from engine import Engine  # noqa: E402
from sources.base import PricePoint  # noqa: E402


class FakeSource:
    def __init__(self):
        self.prices: dict[str, float] = {}

    def set(self, prices: dict[str, float]):
        self.prices = prices

    async def fetch(self):
        return [PricePoint(asset=a, price=p) for a, p in self.prices.items()]


def make_engine(cooldown: int) -> Engine:
    if os.path.exists(config.DB_PATH):
        os.remove(config.DB_PATH)
    db = DB(config.DB_PATH)
    engine = Engine(db, FakeSource(), cooldown=cooldown)
    engine.seed_state()
    return engine


async def test_crossing_dedup_reset():
    eng = make_engine(cooldown=0)
    eng.db.add_subscription(1, "BTC", "gt", 50000.0)

    eng.source.set({"BTC": 40000.0})
    assert await eng.tick() == 0, "未达标不应触发"

    eng.source.set({"BTC": 60000.0})
    assert await eng.tick() == 1, "向上穿越应触发 1 次"

    eng.source.set({"BTC": 65000.0})
    assert await eng.tick() == 0, "持续达标不应重复触发"

    eng.source.set({"BTC": 40000.0})
    assert await eng.tick() == 0, "回落不触发"

    eng.source.set({"BTC": 60000.0})
    assert await eng.tick() == 1, "回落后再穿越应再次触发"
    eng.db.close()

    print("✅ 穿越检测 / 去重 / 回落重置 通过")


async def test_cooldown():
    eng = make_engine(cooldown=3600)
    eng.db.add_subscription(2, "ETH", "gt", 100.0)

    eng.source.set({"ETH": 200.0})
    assert await eng.tick() == 1, "首穿触发"

    eng.source.set({"ETH": 50.0})
    await eng.tick()                      # 回落复位
    eng.source.set({"ETH": 200.0})
    assert await eng.tick() == 0, "冷却期内(3600s)再次穿越不应触发"
    eng.db.close()

    print("✅ 冷却逻辑 通过")


async def test_lt_direction():
    eng = make_engine(cooldown=0)
    eng.db.add_subscription(3, "BTC", "lt", 100.0)

    eng.source.set({"BTC": 200.0})
    assert await eng.tick() == 0, "高于阈值不应触发低于提醒"

    eng.source.set({"BTC": 80.0})
    assert await eng.tick() == 1, "向下穿越低于阈值应触发"
    eng.db.close()

    print("✅ 低于方向 通过")


async def main():
    await test_crossing_dedup_reset()
    await test_cooldown()
    await test_lt_direction()
    print("🎉 全部断言通过")


asyncio.run(main())
