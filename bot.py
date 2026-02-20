import time
import sqlite3
import pyotp
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

TOKEN = "8236670120:AAF6avC-K9345BqyiTE-8QkTew16Ux_EMZQ"
DB_NAME = "bot.db"

# ================= DATABASE =================
conn = sqlite3.connect(DB_NAME, check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    name TEXT,
    secret TEXT
)
""")
conn.commit()

# ================= HELPERS =================
def remaining_time():
    return 30 - int(time.time()) % 30

def normalize_base32(secret):
    s = secret.replace(" ", "").upper()
    if len(s) % 8:
        s += "=" * (8 - len(s) % 8)
    return s

# ================= KEYBOARDS =================
def kb_live(can_save: bool):
    rows = []
    if can_save:
        rows.append([InlineKeyboardButton("💾 Save Key", callback_data="save")])
    rows.append([InlineKeyboardButton("📂 Saved Keys", callback_data="list")])
    return InlineKeyboardMarkup(rows)

def kb_after_expire(can_save: bool):
    rows = [[InlineKeyboardButton("♻️ Refresh Code", callback_data="refresh")]]
    if can_save:
        rows.append([InlineKeyboardButton("💾 Save Key", callback_data="save")])
    rows.append([InlineKeyboardButton("📂 Saved Keys", callback_data="list")])
    return InlineKeyboardMarkup(rows)

def kb_saved_only():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 Saved Keys", callback_data="list")]
    ])

# ================= LIVE TIMER =================
async def start_live_timer(msg, secret, label=None, can_save=True):
    while True:
        rem = remaining_time()
        code = pyotp.TOTP(secret).now()

        header = "🗝️ *KEY ACTIVE*\n\n"
        if label:
            header += f"👉 *NOW :* _{label}_\n\n"

        text = (
            f"{header}"
            "*BOT BY FAHIM*\n"
            "────────────\n"
            f"🔐 *CODE :* `{code}`\n"
            "────────────\n"
            f"⏳ *Time left : | {rem} | seconds*\n"
            "────────────\n\n"
            "✅ *ADMIN 👉 @mdfahim73*"
        )

        # ⏳ Live countdown (NO refresh)
        if rem > 1:
            try:
                await msg.edit_text(
                    text,
                    parse_mode="Markdown",
                    reply_markup=kb_live(can_save)
                )
            except:
                break
            await asyncio.sleep(1)
            continue

        # ⏱️ Time expired (Refresh returns)
        try:
            await msg.edit_text(
                text,
                parse_mode="Markdown",
                reply_markup=kb_after_expire(can_save)
            )
        except:
            pass
        break

# ================= BOT LOGIC =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔐 Send your *AUTHENTICATION KEY* 🗝️ :",
        parse_mode="Markdown",
        reply_markup=kb_saved_only()
    )

async def save_secret(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    # Save name flow
    if context.user_data.get("waiting_name"):
        secret = context.user_data.get("pending_secret")
        cur.execute(
            "INSERT INTO keys (user_id, name, secret) VALUES (?,?,?)",
            (uid, text, secret)
        )
        conn.commit()
        context.user_data.clear()
        await update.message.reply_text(
            f"✅ Saved as *{text}*",
            parse_mode="Markdown",
            reply_markup=kb_saved_only()
        )
        return

    # New secret
    try:
        secret = normalize_base32(text)
        pyotp.TOTP(secret).now()

        msg = await update.message.reply_text("⏳ Loading...")

        context.user_data[msg.message_id] = {
            "secret": secret,
            "label": None,
            "can_save": True
        }

        asyncio.create_task(start_live_timer(msg, secret, None, True))

    except:
        await update.message.reply_text(
            "❌ Invalid Secret Key!",
            reply_markup=kb_saved_only()
        )

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    mid = q.message.message_id
    data = q.data

    data_pack = context.user_data.get(mid)

    # Refresh
    if data == "refresh" and data_pack:
        asyncio.create_task(
            start_live_timer(
                q.message,
                data_pack["secret"],
                data_pack["label"],
                data_pack["can_save"]
            )
        )
        return

    # Save
    if data == "save" and data_pack:
        context.user_data["pending_secret"] = data_pack["secret"]
        context.user_data["waiting_name"] = True
        await q.message.reply_text(
            "✅ *ENTER THE KEY NAME:*",
            parse_mode="Markdown"
        )
        return

    # List
    if data == "list":
        cur.execute("SELECT name FROM keys WHERE user_id=?", (uid,))
        rows = cur.fetchall()

        if not rows:
            await q.answer("📭 No saved keys", show_alert=True)
            return

        kb = [[InlineKeyboardButton(f"🔐 {r[0]}", callback_data=f"use:{r[0]}")] for r in rows]
        kb.append([
            InlineKeyboardButton("🗑️ Delete", callback_data="delmenu"),
            InlineKeyboardButton("👁 Show Key", callback_data="showmenu")
        ])

        await q.message.reply_text(
            "📂 *Saved Keys:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )

    # Use saved key
    elif data.startswith("use:"):
        name = data.split(":", 1)[1]
        cur.execute("SELECT secret FROM keys WHERE user_id=? AND name=?", (uid, name))
        row = cur.fetchone()

        if row:
            msg = await q.message.reply_text("⏳ Loading...")

            context.user_data[msg.message_id] = {
                "secret": row[0],
                "label": name,
                "can_save": False
            }

            asyncio.create_task(start_live_timer(msg, row[0], name, False))

    # Delete
    elif data == "delmenu":
        cur.execute("SELECT name FROM keys WHERE user_id=?", (uid,))
        rows = cur.fetchall()

        kb = [[InlineKeyboardButton(f"❌ {r[0]}", callback_data=f"del:{r[0]}")] for r in rows]

        await q.message.reply_text(
            "🗑️ *Select key to delete:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )

    elif data.startswith("del:"):
        name = data.split(":", 1)[1]
        cur.execute("DELETE FROM keys WHERE user_id=? AND name=?", (uid, name))
        conn.commit()

        await q.message.reply_text(
            f"🗑️ Deleted *{name}*",
            parse_mode="Markdown",
            reply_markup=kb_saved_only()
        )

    # Show
    elif data == "showmenu":
        cur.execute("SELECT name FROM keys WHERE user_id=?", (uid,))
        rows = cur.fetchall()

        kb = [[InlineKeyboardButton(f"👁 {r[0]}", callback_data=f"show:{r[0]}")] for r in rows]

        await q.message.reply_text(
            "👁 *Select key:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )

    elif data.startswith("show:"):
        name = data.split(":", 1)[1]
        cur.execute("SELECT secret FROM keys WHERE user_id=? AND name=?", (uid, name))
        row = cur.fetchone()

        if row:
            await q.message.reply_text(
                f"🔑 *{name}*\n\n`{row[0]}`",
                parse_mode="Markdown",
                reply_markup=kb_saved_only()
            )

# ================= RUN =================
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_secret))
app.add_handler(CallbackQueryHandler(buttons))

print("🤖 Live OTP Bot — FINAL VERSION")
app.run_polling()