"""入口:装配 bot + JobQueue,接线 engine 与通知。

运行方式:
  python main.py                          # 正常模式(需 BOT_TOKEN,可选 HTTPS_PROXY)
  DRY_RUN=1 python main.py                # 离线演练:不连 Telegram,跑 3 轮看触发
"""
import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

import config
from db import DB
from engine import Engine
from notify import init_sender
from sources.price_gateio import GateIoPriceSource
from sources.rss_feed import RSSFeedSource
from sources.whale_alert import WhaleAlertSource
from telegram.request import HTTPXRequest
from ui import UI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

DRY_RUN_TICKS = 3


def build_sources(db: DB) -> dict:
    """组装数据源:价格源必开,巨鲸源在有 key 时启用,RSS 源按订阅自适应。"""
    proxy = config.HTTPS_PROXY or None
    sources: dict = {"price": GateIoPriceSource(proxy=proxy)}
    if config.WHALEALERT_API_KEY:
        sources["whale"] = WhaleAlertSource(api_key=config.WHALEALERT_API_KEY, proxy=proxy)
        logger.info("巨鲸数据源已启用(WhaleAlert)")
    else:
        logger.info("未配置 WHALEALERT_API_KEY,巨鲸类别暂不可用")
    sources["rss"] = RSSFeedSource(
        feed_provider=lambda: [
            s["asset"] for s in db.list_subscriptions() if s["category"] == "rss"
        ],
        proxy=proxy,
    )
    return sources


def build_sender(app):
    async def sender(user_id: int, text: str, sub_id: int):
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"🗑️ 删除 #{sub_id}", callback_data=f"del:{sub_id}"),
        ]])
        try:
            await app.bot.send_message(chat_id=user_id, text=text, reply_markup=kb)
        except Exception as exc:
            logger.warning("推送失败 user=%s: %s", user_id, exc)

    return sender


async def run_dry_run():
    db = DB(config.DB_PATH)
    engine = Engine(db, build_sources(db), cooldown=config.COOLDOWN_SECONDS)
    engine.seed_state()
    subs = db.list_subscriptions()
    logger.info("DRY_RUN 模式:现有订阅 %d 条,跑 %d 轮(间隔 %ss)", len(subs), DRY_RUN_TICKS, config.POLL_INTERVAL)
    if not subs:
        print("提示:数据库暂无订阅,可先运行 tests/seed_test.py 造数据,或直接看下面拉取是否正常。")
    for i in range(DRY_RUN_TICKS):
        print(f"--- 第 {i + 1} 轮 ---")
        fired = await engine.tick()
        print(f"第 {i + 1} 轮触发 {fired} 条")
        if i < DRY_RUN_TICKS - 1:
            await asyncio.sleep(min(config.POLL_INTERVAL, 3))
    print("\nDRY_RUN 结束:若首轮触发、后续轮不重复,则穿越检测/去重正常。")
    db.close()


async def main():
    if config.DRY_RUN:
        await run_dry_run()
        return

    if not config.BOT_TOKEN:
        raise SystemExit("缺少 BOT_TOKEN:请在 .env 中配置,或从 @BotFather 获取后粘贴")

    db = DB(config.DB_PATH)
    engine = Engine(db, build_sources(db), cooldown=config.COOLDOWN_SECONDS)
    engine.seed_state()
    ui = UI(db)

    # Telegram 客户端:显式指定代理,trust_env=False 避免被系统代理劫持
    request = HTTPXRequest(
        proxy=config.HTTPS_PROXY or None,
        connect_timeout=10.0,
        httpx_kwargs={"trust_env": False},
    )
    builder = ApplicationBuilder().token(config.BOT_TOKEN).request(request)
    app = builder.build()

    init_sender(build_sender(app))

    app.add_handler(CommandHandler("start", ui.cmd_start))
    app.add_handler(CommandHandler("myalerts", ui.cmd_my_alerts))
    app.add_handler(CallbackQueryHandler(ui.on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ui.on_text))

    async def job_tick(context):
        await engine.tick()

    app.job_queue.run_repeating(job_tick, interval=config.POLL_INTERVAL, first=5)

    logger.info("Bot 启动:轮询间隔 %ss,数据源 Gate.io,代理=%s", config.POLL_INTERVAL, config.HTTPS_PROXY or "直连")
    await app.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
