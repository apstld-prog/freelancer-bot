import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)
from db import get_session
from sqlalchemy import text
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

BOT_TOKEN = os.getenv("BOT_TOKEN")

def build_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Saved Jobs", callback_data="act:saved")],
        [InlineKeyboardButton("🧩 Admin", callback_data="act:admin")]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Freelancer Alert Bot!",
        reply_markup=build_main_keyboard()
    )

async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id
    with get_session() as s:
        user = s.execute(
            text("SELECT id, is_admin FROM \"user\" WHERE telegram_id=:t"),
            {"t": uid}
        ).fetchone()
        if user:
            status = "✅ Admin" if user.is_admin else "👤 User"
            await update.message.reply_text(f"Your ID: {uid}\nStatus: {status}")
        else:
            await update.message.reply_text("You are not registered.")

async def feedstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        rows = s.execute(
            text("SELECT platform, COUNT(*) FROM feed_events "
                 "WHERE created_at > NOW() - INTERVAL '24 hours' "
                 "GROUP BY platform")
        ).fetchall()
        if not rows:
            await update.message.reply_text("No events in the last 24 hours.")
            return
        msg = "\n".join([f"• {r[0]}: {r[1]}" for r in rows])
        await update.message.reply_text(msg)

def build_application():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("whoami", whoami))
    app.add_handler(CommandHandler("feedstatus", feedstatus))
    return app
