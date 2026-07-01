import sqlite3
import re
from datetime import datetime, timedelta

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import os

TOKEN = os.getenv("TOKEN")

# ================= DB =================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    type TEXT,
    content TEXT,
    created_at TEXT
)
""")
conn.commit()


# ================= 主键盘 =================
main_kb = ReplyKeyboardMarkup([
    ["📋 已查模板", "💰 已转模板"],
    ["📒 客户列表", "🔍 客户搜索"],
    ["📊 入款统计", "🧹 清空数据"]
], resize_keyboard=True)


# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 刘烨的专属记账系统已启动", reply_markup=main_kb)


# ================= 模板 =================
async def template_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "📋 已查模板":
        tpl = """客户ID：
钱包：
余额：
锁屏密码：
支付密码：
备注："""
        context.user_data["mode"] = "check"
        await update.message.reply_text(tpl)

    elif text == "💰 已转模板":
        tpl = """日期：
客户ID：
入款金额：
钱包余额：
锁屏密码：
支付密码："""
        context.user_data["mode"] = "transfer"
        await update.message.reply_text(tpl)


# ================= 保存 + 编辑 =================
async def save_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.message.from_user.id

    # ===== 编辑模式 =====
    if "edit_id" in context.user_data:
        cid = context.user_data["edit_id"]

        cur.execute("""
            UPDATE users_data
            SET content=?
            WHERE id=? AND user_id=?
        """, (text, cid, user_id))

        conn.commit()
        context.user_data["edit_id"] = None

        await update.message.reply_text("✅ 已更新")
        return

    # ===== 精准客户ID搜索（已升级）=====
    if context.user_data.get("mode") == "search_id":
        cid = text.strip()

        if not cid:
            await update.message.reply_text("请输入客户ID")
            return

        cur.execute("""
            SELECT id, type, content
            FROM users_data
            WHERE user_id=? AND content LIKE ?
            ORDER BY id DESC
            LIMIT 1
        """, (user_id, f"%客户ID：{cid}%"))

        row = cur.fetchone()

        if not row:
            await update.message.reply_text("❌ 未找到该客户ID")
            context.user_data["mode"] = None
            return

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✏️ 修改", callback_data=f"edit_{row[0]}"),
                InlineKeyboardButton("🗑 删除", callback_data=f"del_{row[0]}")
            ]
        ])

        await update.message.reply_text(
            f"📄 精准匹配客户\n\nID:{row[0]}\n类型:{row[1]}\n\n{row[2]}",
            reply_markup=kb
        )

        context.user_data["mode"] = None
        return

    # ===== 新增模式 =====
    mode = context.user_data.get("mode")

    if mode not in ["check", "transfer"]:
        return

    cur.execute("""
        INSERT INTO users_data (user_id, type, content, created_at)
        VALUES (?, ?, ?, ?)
    """, (user_id, mode, text, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    conn.commit()
    context.user_data["mode"] = None

    await update.message.reply_text("✅ 已保存")


# ================= 客户列表 =================
async def list_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = ReplyKeyboardMarkup([
        ["📋 已查客户", "💰 已转客户"],
        ["🔙 返回"]
    ], resize_keyboard=True)

    await update.message.reply_text("📒 请选择客户类型", reply_markup=kb)


async def list_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text

    if text == "🔙 返回":
        await update.message.reply_text("已返回", reply_markup=main_kb)
        return

    if text == "📋 已查客户":
        t = "check"
    elif text == "💰 已转客户":
        t = "transfer"
    else:
        return

    cur.execute("""
        SELECT id, content
        FROM users_data
        WHERE user_id=? AND type=?
        ORDER BY id DESC
        LIMIT 20
    """, (user_id, t))

    rows = cur.fetchall()

    if not rows:
        await update.message.reply_text("暂无数据")
        return

    msg = f"📒 {text}\n\n"
    for r in rows:
        msg += f"ID:{r[0]}\n{r[1]}\n------\n"

    await update.message.reply_text(msg)


# ================= 搜索入口 =================
async def search_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = "search_id"
    await update.message.reply_text("🔍 请输入客户ID")


# ================= 入款统计 =================
async def stats_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = ReplyKeyboardMarkup([
        ["今日", "昨日"],
        ["本月", "本年"],
        ["🔙 返回"]
    ], resize_keyboard=True)

    await update.message.reply_text("📊 请选择时间范围", reply_markup=kb)


def get_range(key):
    now = datetime.now()

    if key == "今日":
        start = now.replace(hour=0, minute=0, second=0)
        end = now
    elif key == "昨日":
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0)
        end = start + timedelta(days=1)
    elif key == "本月":
        start = now.replace(day=1, hour=0, minute=0, second=0)
        end = now
    elif key == "本年":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0)
        end = now
    else:
        start = now
        end = now

    return start, end


async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text

    if text == "🔙 返回":
        await update.message.reply_text("已返回", reply_markup=main_kb)
        return

    if text not in ["今日", "昨日", "本月", "本年"]:
        return

    start, end = get_range(text)

    cur.execute("""
        SELECT content, created_at
        FROM users_data
        WHERE user_id=? AND type='transfer'
    """, (user_id,))

    rows = cur.fetchall()

    total = 0
    detail = ""

    for content, created_at in rows:
        try:
            dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
        except:
            continue

        if start <= dt <= end:
            m = re.search(r"入款金额：\s*(\d+)", content)
            if m:
                total += int(m.group(1))
                detail += f"{created_at}\n{content}\n------\n"

    msg = f"💰 {text}总入款：{total}\n\n{detail if detail else '无明细'}"

    await update.message.reply_text(msg)


# ================= 按钮（修改/删除） =================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    # 删除
    if data.startswith("del_"):
        cid = data.split("_")[1]

        cur.execute("""
            DELETE FROM users_data
            WHERE id=? AND user_id=?
        """, (cid, user_id))

        conn.commit()
        await query.edit_message_text("🗑 已删除")
        return

    # 修改
    if data.startswith("edit_"):
        cid = data.split("_")[1]

        cur.execute("""
            SELECT content
            FROM users_data
            WHERE id=? AND user_id=?
        """, (cid, user_id))

        row = cur.fetchone()

        if not row:
            await query.edit_message_text("未找到")
            return

        context.user_data["edit_id"] = cid

        await query.edit_message_text(
            f"✏️ 修改内容：\n\n{row[0]}\n\n请直接发送新内容"
        )
        return


# ================= 清空 =================
async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    cur.execute("DELETE FROM users_data WHERE user_id=?", (user_id,))
    conn.commit()

    await update.message.reply_text("🧹 已清空")


# ================= MAIN =================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))

app.add_handler(MessageHandler(filters.Regex("模板"), template_handler))

app.add_handler(MessageHandler(filters.Regex("客户列表"), list_menu))
app.add_handler(MessageHandler(filters.Regex("已查客户|已转客户|返回"), list_data))

app.add_handler(MessageHandler(filters.Regex("客户搜索"), search_entry))

app.add_handler(MessageHandler(filters.Regex("入款统计"), stats_menu))
app.add_handler(MessageHandler(filters.Regex("今日|昨日|本月|本年|返回"), stats_handler))

app.add_handler(MessageHandler(filters.Regex("清空数据"), clear))

app.add_handler(CallbackQueryHandler(button_handler))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_data))

print("Bot running...")
app.run_polling()
