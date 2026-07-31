"""Telegram 交互:命令 + 内联键盘 + 回调。"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from db import DB

# 本期支持的币种(后续可扩展)
SUPPORTED_ASSETS = ["BTC", "ETH", "SOL", "BNB", "DOGE", "XRP", "ADA", "LTC"]


def _category_menu() -> InlineKeyboardMarkup:
    # 顶层入口:预留未来多类别(新闻/GitHub/论文…)
    kb = [[InlineKeyboardButton("🪙 加密货币价格提醒", callback_data="cat:price")]]
    return InlineKeyboardMarkup(kb)


def _asset_kb() -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(SUPPORTED_ASSETS), 3):
        rows.append(
            [InlineKeyboardButton(a, callback_data=f"asset:{a}") for a in SUPPORTED_ASSETS[i : i + 3]]
        )
    return InlineKeyboardMarkup(rows)


def _op_kb() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("📈 高于阈值", callback_data="op:gt"),
         InlineKeyboardButton("📉 低于阈值", callback_data="op:lt")],
    ]
    return InlineKeyboardMarkup(kb)


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
            "选择类别,设置币种与阈值,价格穿越时自动推送提醒。",
            reply_markup=_category_menu(),
        )

    async def cmd_my_alerts(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        subs = self.db.list_subscriptions(update.effective_user.id)
        if not subs:
            await update.message.reply_text("还没有提醒,点下方添加 👇", reply_markup=_category_menu())
            return
        lines, rows = [], []
        for s in subs:
            op_cn = "高于" if s["op"] == "gt" else "低于"
            lines.append(f"#{s['id']}  {s['asset']} {op_cn} ${s['threshold']:,.2f}")
            rows.append(
                [InlineKeyboardButton(f"🗑️ 删除 #{s['id']} {s['asset']}", callback_data=f"del:{s['id']}")]
            )
        await update.message.reply_text(
            "📋 我的提醒\n" + "\n".join(lines), reply_markup=InlineKeyboardMarkup(rows)
        )

    # ---------- 内联回调 ----------
    async def on_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        if data.startswith("cat:"):
            await query.edit_message_text("选择要监控的币种:", reply_markup=_asset_kb())
        elif data.startswith("asset:"):
            context.user_data["asset"] = data.split(":", 1)[1]
            await query.edit_message_text(
                f"{context.user_data['asset']}: 价格达到什么条件时提醒?", reply_markup=_op_kb()
            )
        elif data.startswith("op:"):
            context.user_data["op"] = data.split(":", 1)[1]
            asset = context.user_data.get("asset", "?")
            op_cn = "高于" if context.user_data["op"] == "gt" else "低于"
            await query.edit_message_text(
                f"请输入阈值价格(数字,如 65000)\n当前选择:{asset} {op_cn} 阈值"
            )
        elif data.startswith("del:"):
            sub_id = int(data.split(":", 1)[1])
            ok = self.db.delete_subscription(sub_id, query.from_user.id)
            await query.edit_message_text("已删除 ✅" if ok else "删除失败或已不存在")

    # ---------- 文本输入(阈值) ----------
    async def on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        ud = context.user_data
        if "asset" not in ud or "op" not in ud:
            return  # 不在输入流程中,忽略
        try:
            threshold = float(update.message.text.replace(",", "").replace("$", ""))
        except ValueError:
            await update.message.reply_text("请输入数字,例如 65000")
            return
        asset, op = ud["asset"], ud["op"]
        sub_id = self.db.add_subscription(update.effective_user.id, asset, op, threshold)
        ud.clear()
        op_cn = "高于" if op == "gt" else "低于"
        await update.message.reply_text(
            f"✅ 已添加提醒\n{asset} {op_cn} ${threshold:,.2f}\n(订阅 #{sub_id})",
            reply_markup=_category_menu(),
        )
