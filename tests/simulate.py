"""交互式模拟器:无需 BOT_TOKEN,用真实数据源 + 真实引擎模拟用户会话。

用法:PYTHONPATH=. .venv/Scripts/python tests/simulate.py

命令:
  price <币种> <gt|lt> <阈值>    添加价格提醒,如 price BTC gt 50000
  whale <币种|ANY> <最小USD>     添加巨鲸提醒(需 .env 配 WHALEALERT_API_KEY)
  rss <URL> [关键词...]          添加 RSS 订阅,如 rss https://rsshub.app/bbc/subscription ai
  list                           查看全部订阅
  del <id>                       删除订阅
  clear                          清空订阅
  fire [次数]                    跑轮询 N 次,控制台显示"即将推送"的消息
  help / exit                    帮助 / 退出

说明:DRY_RUN 模式,不会真的发送 Telegram;触发时打印的即是推给用户的消息。
"""
import asyncio
import os
import tempfile

os.environ["DRY_RUN"] = "1"
os.environ["DB_PATH"] = os.path.join(tempfile.gettempdir(), "simulate.db")
os.environ["COOLDOWN_SECONDS"] = "0"  # 模拟器关冷却,便于观察触发

import config  # noqa: E402
from db import DB  # noqa: E402
from engine import Engine  # noqa: E402
from sources.price_gateio import GateIoPriceSource  # noqa: E402
from sources.rss_feed import RSSFeedSource  # noqa: E402
from sources.whale_alert import WhaleAlertSource  # noqa: E402

FAKE_USER = 100  # 模拟用户 ID

HELP = """🧪 模拟器(不发送真实 Telegram 消息)
──────────────────────────────────────
price BTC gt 50000       # 价格:币种 方向(gt/lt) 阈值
whale ANY 1000000        # 巨鲸:范围(币种/ANY) 最小USD
rss <URL> [关键词...]     # RSS:链接 + 可选关键词
list                     # 查看订阅
del <id>                 # 删除订阅
clear                    # 清空订阅
fire [次数]               # 跑轮询,显示触发的推送
help | exit
──────────────────────────────────────"""


def build_sources(db):
    proxy = config.HTTPS_PROXY or None
    sources = {"price": GateIoPriceSource(proxy=proxy)}
    if config.WHALEALERT_API_KEY:
        sources["whale"] = WhaleAlertSource(api_key=config.WHALEALERT_API_KEY, proxy=proxy)
    else:
        print("ℹ️  未配置 WHALEALERT_API_KEY,whale 命令不可用(价格/RSS 不受影响)")
    sources["rss"] = RSSFeedSource(
        feed_provider=lambda: [s["asset"] for s in db.list_subscriptions() if s["category"] == "rss"],
        proxy=proxy,
    )
    return sources


async def main():
    if os.path.exists(config.DB_PATH):
        os.remove(config.DB_PATH)
    db = DB(config.DB_PATH)
    engine = Engine(db, build_sources(db), cooldown=config.COOLDOWN_SECONDS)
    engine.seed_state()
    print(HELP)

    while True:
        try:
            line = input("你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见 👋")
            break
        if not line:
            continue
        parts = line.split()
        cmd = parts[0].lower()
        try:
            if cmd in ("exit", "quit", "q"):
                print("再见 👋")
                break
            elif cmd == "help":
                print(HELP)
            elif cmd == "clear":
                for s in db.list_subscriptions():
                    db.delete_subscription(s["id"], FAKE_USER)
                print("已清空全部订阅")
            elif cmd == "list":
                subs = db.list_subscriptions()
                if not subs:
                    print("暂无订阅")
                for s in subs:
                    desc = _sub_desc(s)
                    print(f"  #{s['id']}  {desc}")
            elif cmd == "del" and len(parts) == 2:
                print("已删除 ✅" if db.delete_subscription(int(parts[1]), FAKE_USER) else "删除失败")
            elif cmd == "price" and len(parts) >= 4 and parts[2] in ("gt", "lt"):
                sid = db.add_subscription(FAKE_USER, "price", parts[1], parts[2], float(parts[3]))
                print(f"✅ 添加价格提醒 #{sid}: {parts[1].upper()} {parts[2]} {parts[3]}")
            elif cmd == "whale" and len(parts) >= 3:
                sid = db.add_subscription(FAKE_USER, "whale", parts[1], "gt", float(parts[2]))
                print(f"✅ 添加巨鲸提醒 #{sid}")
            elif cmd == "rss" and len(parts) >= 2:
                url = parts[1]
                kw = " ".join(parts[2:])
                sid = db.add_subscription(FAKE_USER, "rss", url, "contains", 0.0, filter=kw)
                print(f"✅ 添加 RSS 订阅 #{sid}: {url} 关键词:{kw or '全部'}")
            elif cmd == "fire":
                n = int(parts[1]) if len(parts) > 1 else 1
                for i in range(n):
                    print(f"--- 第 {i + 1} 次轮询 ---")
                    await engine.tick()
                    await asyncio.sleep(1)
            else:
                print("未知命令,输入 help 查看用法")
        except Exception as exc:
            print(f"⚠️  出错: {exc}")


def _sub_desc(s: dict) -> str:
    if s["category"] == "whale":
        scope = "全部币种" if s["asset"] == "ANY" else s["asset"]
        return f"🐋 {scope} ≥ ${s['threshold']:,.0f}"
    if s["category"] == "rss":
        url = s["asset"]
        short = url if len(url) <= 32 else url[:29] + "…"
        kw = f" · {s['filter']}" if s.get("filter") else ""
        return f"📰 {short}{kw}"
    op_cn = "高于" if s["op"] == "gt" else "低于"
    return f"🪙 {s['asset']} {op_cn} ${s['threshold']:,.2f}"


if __name__ == "__main__":
    asyncio.run(main())
