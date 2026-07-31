"""断言测试:价格穿越/去重/冷却/低于方向 + 巨鲸过滤/去重/冷却。用假数据源,不联网。

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
from sources.base import AlertItem  # noqa: E402


class FakeSource:
    def __init__(self, category: str = "price"):
        self.category = category
        self.items: list[AlertItem] = []

    def set_prices(self, prices: dict[str, float]):
        self.items = [
            AlertItem(category="price", key=a, asset=a, value=p) for a, p in prices.items()
        ]

    def set_whales(self, whales: list[dict]):
        self.items = [
            AlertItem(
                category="whale",
                key=w["key"],
                asset=w["asset"],
                value=w["usd"],
                extra=w.get("extra", {}),
            )
            for w in whales
        ]

    async def fetch(self):
        return list(self.items)


def make_engine(cooldown: int, category: str = "price") -> Engine:
    if os.path.exists(config.DB_PATH):
        os.remove(config.DB_PATH)
    db = DB(config.DB_PATH)
    engine = Engine(db, {category: FakeSource(category)}, cooldown=cooldown)
    engine.seed_state()
    return engine


async def test_crossing_dedup_reset():
    eng = make_engine(cooldown=0)
    eng.db.add_subscription(1, "price", "BTC", "gt", 50000.0)
    src = eng.sources["price"]

    src.set_prices({"BTC": 40000.0})
    assert await eng.tick() == 0, "未达标不应触发"

    src.set_prices({"BTC": 60000.0})
    assert await eng.tick() == 1, "向上穿越应触发 1 次"

    src.set_prices({"BTC": 65000.0})
    assert await eng.tick() == 0, "持续达标不应重复触发"

    src.set_prices({"BTC": 40000.0})
    assert await eng.tick() == 0, "回落不触发"

    src.set_prices({"BTC": 60000.0})
    assert await eng.tick() == 1, "回落后再穿越应再次触发"
    eng.db.close()

    print("✅ 价格 穿越检测 / 去重 / 回落重置 通过")


async def test_cooldown():
    eng = make_engine(cooldown=3600)
    eng.db.add_subscription(2, "price", "ETH", "gt", 100.0)
    src = eng.sources["price"]

    src.set_prices({"ETH": 200.0})
    assert await eng.tick() == 1, "首穿触发"

    src.set_prices({"ETH": 50.0})
    await eng.tick()                      # 回落复位
    src.set_prices({"ETH": 200.0})
    assert await eng.tick() == 0, "冷却期内(3600s)再次穿越不应触发"
    eng.db.close()

    print("✅ 价格 冷却逻辑 通过")


async def test_lt_direction():
    eng = make_engine(cooldown=0)
    eng.db.add_subscription(3, "price", "BTC", "lt", 100.0)
    src = eng.sources["price"]

    src.set_prices({"BTC": 200.0})
    assert await eng.tick() == 0, "高于阈值不应触发低于提醒"

    src.set_prices({"BTC": 80.0})
    assert await eng.tick() == 1, "向下穿越低于阈值应触发"
    eng.db.close()

    print("✅ 价格 低于方向 通过")


async def test_whale_filter_dedup():
    eng = make_engine(cooldown=0, category="whale")
    eng.db.add_subscription(1, "whale", "ANY", "gt", 1_000_000.0)
    eng.db.add_subscription(2, "whale", "BTC", "gt", 1_000_000.0)
    src = eng.sources["whale"]

    # 不达标 / 不匹配币种 → 0
    src.set_whales([{"key": "h1", "asset": "ETH", "usd": 500_000}])
    assert await eng.tick() == 0, "低于阈值不应触发"

    # 达标 BTC 交易:ANY + BTC 两个订阅都命中 → 2
    src.set_whales([{"key": "h2", "asset": "BTC", "usd": 2_000_000}])
    assert await eng.tick() == 2, "同一条交易应同时命中 ANY 与 BTC 订阅"

    # 同一条交易再次出现 → 引擎级去重 → 0
    src.set_whales([{"key": "h2", "asset": "BTC", "usd": 2_000_000}])
    assert await eng.tick() == 0, "重复交易不应再次触发"
    eng.db.close()

    print("✅ 巨鲸 过滤 / 去重 通过")


async def test_whale_cooldown():
    eng = make_engine(cooldown=3600, category="whale")
    eng.db.add_subscription(3, "whale", "ANY", "gt", 1_000_000.0)
    src = eng.sources["whale"]

    src.set_whales([{"key": "a", "asset": "BTC", "usd": 2_000_000}])
    assert await eng.tick() == 1, "首条巨鲸触发"

    src.set_whales([{"key": "b", "asset": "BTC", "usd": 2_000_000}])
    assert await eng.tick() == 0, "冷却期内新交易不应触发"
    eng.db.close()

    print("✅ 巨鲸 冷却 通过")


async def main():
    await test_crossing_dedup_reset()
    await test_cooldown()
    await test_lt_direction()
    await test_whale_filter_dedup()
    await test_whale_cooldown()
    print("🎉 全部断言通过")


asyncio.run(main())
