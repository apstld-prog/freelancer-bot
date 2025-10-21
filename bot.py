import os
import logging
import json
import asyncio
from datetime import datetime, timedelta
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    MessageHandler, filters, CallbackQueryHandler, ConversationHandler
)
from config import BOT_TOKEN
from utils import (
    load_users, save_users, load_keywords, save_keywords,
    load_settings, save_settings, format_jobs, is_admin,
)

# -----------------------------------------------------
# Logging setup
# -----------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -----------------------------------------------------
# Global Data
# -----------------------------------------------------
USERS = load_users()
KEYWORDS = load_keywords()
SETTINGS = load_settings()

FREE_TRIAL_DAYS = 10

# -----------------------------------------------------
# Helpers
# -----------------------------------------------------
def get_main_menu():
    return ReplyKeyboardMarkup(
        [
            ["➕ Add Keywords", "⚙️ Settings"],
            ["📖 Help", "💾 Saved"],
            ["📩 Contact", "🧩 Admin"]
        ],
        resize_keyboard=True
    )

def is_trial_expired(user):
    if "joined" not in user:
        return True
    joined = datetime.fromisoformat(user["joined"])
    return datetime.now() > joined + timedelta(days=FREE_TRIAL_DAYS)

# -----------------------------------------------------
# Core Bot Commands
# -----------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in USERS:
        USERS[user.id] = {"name": user.first_name, "joined": datetime.now().isoformat()}
        save_users(USERS)

    trial_expired = is_trial_expired(USERS[user.id])
    if trial_expired:
        text = (
            "⛔ Your free trial has expired.\n"
            "Contact admin to renew your access."
        )
    else:
        days_left = FREE_TRIAL_DAYS - (datetime.now() - datetime.fromisoformat(USERS[user.id]["joined"])).days
        text = (
            f"👋 Welcome {user.first_name}!\n"
            f"🎁 You have a {FREE_TRIAL_DAYS}-day free trial.\n"
            f"⏳ Remaining days: {days_left}\n\n"
            f"Use the menu below to explore."
        )

    await update.message.reply_text(text, reply_markup=get_main_menu())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛠 Commands:\n"
        "/start - Restart bot\n"
        "/help - Show help\n"
        "/keywords - View keywords\n"
        "/admin - Admin panel"
    )

async def keywords_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not KEYWORDS:
        await update.message.reply_text("⚠ No keywords found.")
        return
    await update.message.reply_text(
        "📋 Keywords:\n" + "\n".join([f"• {kw}" for kw in KEYWORDS])
    )

# -----------------------------------------------------
# Admin Panel
# -----------------------------------------------------
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 You are not authorized.")
        return

    keyboard = [
        [InlineKeyboardButton("👥 Users", callback_data="show_users")],
        [InlineKeyboardButton("🔑 Keywords", callback_data="show_keywords")],
        [InlineKeyboardButton("🧹 Clear Cache", callback_data="clear_cache")]
    ]
    await update.message.reply_text("🧩 Admin Panel", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "show_users":
        users_list = "\n".join([f"{uid}: {data['name']}" for uid, data in USERS.items()])
        await query.edit_message_text(f"👥 Users:\n{users_list}")
    elif query.data == "show_keywords":
        await query.edit_message_text(f"🔑 Keywords:\n" + "\n".join(KEYWORDS))
    elif query.data == "clear_cache":
        await query.edit_message_text("✅ Cache cleared (simulated).")

# -----------------------------------------------------
# Build and Run
# -----------------------------------------------------
def build_application():
    if not BOT_TOKEN:
        raise ValueError("❌ BOT_TOKEN missing from config.py or environment.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("keywords", keywords_command))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(button_handler))

    return app

if __name__ == "__main__":
    print("✅ Bot starting with config.py token...")
    app = build_application()
    app.run_polling()
