"""Telegram 交互:命令 + 内联键盘 + 回调。"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from db import DB

# 本期支持的币种(后续可扩展)
SUPPORTED_ASSETS = ["BTC", "ETH", "SOL", "BNB", "DOGE", "XRP", "ADA", "LTC"]
# 巨鲸监控范围:"ANY" = 全部币种
WHALE_ASSETS = ["ANY"] + SUPPORTED_ASSETS


def _category_menu() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("🪙 加密货币价格提醒", callback_data="cat:price")],
        [InlineKeyboardButton("🐋 巨鲸转账提醒", callback_data="cat:whale")],
        [InlineKeyboardButton("📰 RSS 订阅", callback_data="cat:rss")],
    ]
    return InlineKeyboardMarkup(kb)


def _asset_kb(assets: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(assets), 3):
        rows.append([InlineKeyboardButton(a, callback_data=f"asset:{a}") for a in assets[i : i + 3]])
    return InlineKeyboardMarkup(rows)


def _op_kb() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("📈 高于阈值", callback_data="op:gt"),
         InlineKeyboardButton("📉 低于阈值", callback_data="op:lt")],
    ]
    return InlineKeyboardMarkup(kb)


def _asset_display(asset: str) -> str:
    return "全部币种" if asset == "ANY" else asset


def _sub_desc(s: dict) -> str:
    """订阅的一行描述,供列表/删除按钮展示。"""
    if s["category"] == "whale":
        return f"🐋 {_asset_display(s['asset'])} ≥ ${s['threshold']:,.0f}"
    if s["category"] == "rss":
        url = s["asset"]
        short = url if len(url) <= 32 else url[:29] + "…"
        kw = f" · {s['filter']}" if s.get("filter") else ""
        return f"📰 {short}{kw}"
    op_cn = "高于" if s["op"] == "gt" else "低于"
    return f"🪙 {s['asset']} {op_cn} ${s['threshold']:,.2f}"


class UI:
    def __init__(self, db: DB):
        self.db = db

    # ---------- 命令 ----------
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user:
            self.db.register_user(user.id, user.username)
        await update.message.reply_text(
            "欢迎使用 ⚡ 加密价格提醒\n\n"
            "选择类别,设置条件,条件命中时自动推送提醒。",
            reply_markup=_category_menu(),
        )

    async def cmd_my_alerts(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        subs = self.db.list_subscriptions(update.effective_user.id)
        if not subs:
            await update.message.reply_text("还没有提醒,点下方添加 👇", reply_markup=_category_menu())
            return
        lines, rows = [], []
        for s in subs:
            lines.append(f"#{s['id']}  {_sub_desc(s)}")
            rows.append(
                [InlineKeyboardButton(f"🗑️ 删除 #{s['id']}", callback_data=f"del:{s['id']}")]
            )
        await update.message.reply_text(
            "📋 我的提醒\n" + "\n".join(lines), reply_markup=InlineKeyboardMarkup(rows)
        )

    # ---------- 内联回调 ----------
    async def on_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        ud = context.user_data

        if data.startswith("cat:"):
            ud["category"] = data.split(":", 1)[1]
            if ud["category"] == "whale":
                await query.edit_message_text(
                    "🐋 选择要监控的范围(全部币种或指定币种):",
                    reply_markup=_asset_kb(WHALE_ASSETS),
                )
            elif ud["category"] == "rss":
                await query.edit_message_text(
                    "📰 请发送一个 RSS/Atom 链接\n(例如 https://rsshub.app/bbc/subscription )"
                )
            else:
                await query.edit_message_text("选择要监控的币种:", reply_markup=_asset_kb(SUPPORTED_ASSETS))

        elif data.startswith("asset:"):
            asset = data.split(":", 1)[1]
            ud["asset"] = asset
            if ud.get("category") == "whale":
                await query.edit_message_text(
                    f"🐋 {_asset_display(asset)}: 请输入最小金额(USD),如 1000000"
                )
            else:
                await query.edit_message_text(f"{asset}: 价格达到什么条件时提醒?", reply_markup=_op_kb())

        elif data.startswith("op:"):
            ud["op"] = data.split(":", 1)[1]
            op_cn = "高于" if ud["op"] == "gt" else "低于"
            await query.edit_message_text(f"请输入阈值价格(数字,如 65000)\n当前选择:{ud['asset']} {op_cn} 阈值")

        elif data.startswith("del:"):
            sub_id = int(data.split(":", 1)[1])
            ok = self.db.delete_subscription(sub_id, query.from_user.id)
            await query.edit_message_text("已删除 ✅" if ok else "删除失败或已不存在")

    # ---------- 文本输入(URL / 关键词 / 阈值) ----------
    async def on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        ud = context.user_data
        if "category" not in ud:
            return  # 不在输入流程中,忽略
        cat = ud["category"]
        raw = update.message.text.strip()

        # --- RSS:两步输入(URL → 关键词) ---
        if cat == "rss":
            if "asset" not in ud:
                if not (raw.startswith("http://") or raw.startswith("https://")):
                    await update.message.reply_text("请输入以 http:// 或 https:// 开头的 RSS 链接")
                    return
                ud["asset"] = raw
                await update.message.reply_text("可选:输入关键词过滤(逗号分隔,如 'ai, 比特币');发送 /skip 跳过")
                return
            kw = "" if raw in ("/skip", "/跳过") else raw
            sub_id = self.db.add_subscription(
                update.effective_user.id, "rss", ud["asset"], "contains", 0.0, filter=kw
            )
            url = ud["asset"]
            short = url if len(url) <= 40 else url[:37] + "…"
            ud.clear()
            await update.message.reply_text(
                f"✅ 已添加 RSS 订阅\n{short}\n关键词: {kw or '(全部)'}\n(订阅 #{sub_id})",
                reply_markup=_category_menu(),
            )
            return

        # --- price / whale:阈值输入 ---
        if "asset" not in ud:
            return
        if cat == "price" and "op" not in ud:
            return
        try:
            threshold = float(raw.replace(",", "").replace("$", ""))
        except ValueError:
            await update.message.reply_text("请输入数字,例如 65000")
            return

        op = ud.get("op", "gt")  # whale 用 >= 语义,gt 占位
        asset = ud["asset"]
        sub_id = self.db.add_subscription(update.effective_user.id, cat, asset, op, threshold)
        ud.clear()

        if cat == "whale":
            msg = f"✅ 已添加提醒\n🐋 巨鲸转账 {_asset_display(asset)} ≥ ${threshold:,.0f}\n(订阅 #{sub_id})"
        else:
            op_cn = "高于" if op == "gt" else "低于"
            msg = f"✅ 已添加提醒\n{asset} {op_cn} ${threshold:,.2f}\n(订阅 #{sub_id})"
        await update.message.reply_text(msg, reply_markup=_category_menu())
