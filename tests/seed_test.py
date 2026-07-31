"""造测试数据:插入几条演示订阅,供 DRY_RUN 验证穿越/去重。"""
import os

os.environ.setdefault("DRY_RUN", "1")

import config  # noqa: E402
from db import DB  # noqa: E402

db = DB(config.DB_PATH)
# 价格:现价远高于阈值 → 首轮必触发
db.add_subscription(123456789, "price", "BTC", "gt", 1000.0)
# 价格:现价远高于阈值 → 永不满足(测"不误报")
db.add_subscription(123456789, "price", "BTC", "lt", 0.0001)
# 价格:另一用户一条
db.add_subscription(987654321, "price", "ETH", "gt", 1.0)
# 巨鲸:全币种 ≥ 100 万美元
db.add_subscription(123456789, "whale", "ANY", "gt", 1_000_000.0)
# RSS:订阅本仓库 release 动态(网络不通时优雅降级)
db.add_subscription(
    123456789, "rss", "https://github.com/lzw-wo/crypto-alert-bot/releases.atom", "contains", 0.0, filter=""
)
print("已写入 5 条测试订阅(users: 123456789 / 987654321)")
db.close()
