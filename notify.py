"""通知:DRY_RUN=1 → 打印控制台 + 写 alerts.log;否则经注入的 sender 推送到 Telegram。"""
import logging
import time

import config

logger = logging.getLogger(__name__)

_sender = None  # 由 main.py 装配 bot 后注入


def init_sender(func):
    """注入真正的发送函数:async def sender(user_id:int, text:str, sub_id:int)。"""
    global _sender
    _sender = func


async def send_alert(user_id: int, sub_id: int, text: str) -> None:
    if config.DRY_RUN:
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] user={user_id} sub={sub_id} {text}\n"
        print(line, end="")
        with open(config.LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    elif _sender:
        await _sender(user_id, text, sub_id)
    else:
        logger.warning("未注入 sender,无法推送: %s", text)
