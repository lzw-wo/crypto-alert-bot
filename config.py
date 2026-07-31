"""集中配置:从 .env / 环境变量读取。"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# 必填:从 @BotFather 创建 bot 后获得
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# 可选:走代理时填,例如 http://127.0.0.1:33210
HTTPS_PROXY = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or ""

# 可选:WhaleAlert API key(https://whale-alert.io 免费注册),填了才启用巨鲸类别
WHALEALERT_API_KEY = os.getenv("WHALEALERT_API_KEY", "")

# 离线演练模式:1 = 不连 Telegram,告警只打印到控制台并写 alerts.log
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"

# 轮询间隔(秒)
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))

# 触发后冷却(秒),防止价格震荡导致的重复轰炸
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "1800"))

# SQLite 数据库路径
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "alerts.db"))

# 离线演练时的告警日志
LOG_FILE = os.getenv("LOG_FILE", str(BASE_DIR / "alerts.log"))
