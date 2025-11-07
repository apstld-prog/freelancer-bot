import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db import get_session, get_or_create_user_by_tid
from config import TRIAL_DAYS
from utils import is_admin_user

log = logging.getLogger(__name__)

def main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Builds main menu with all options and correct emojis."""
    rows = [
        [
            InlineKeyboardButton("➕ Add Keywords", callback_data="act:addkw"),
            InlineKeyboardButton("⚙ Settings", callback_data="act:settings"),
        ],
        [
            InlineKeyboardButton("📊 Feed Status", callback_data="act:feed"),
            InlineKeyboardButton("💾 Saved Jobs", callback_data="act:saved"),
        ],
        [
            InlineKeyboardButton("🆘 Help", callback_data="act:help"),
            InlineKeyboardButton("📨 Contact", callback_data="act:contact"),
        ],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton("👑 Admin", callback_data="act:admin")])
    return InlineKeyboardMarkup(rows)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initial /start handler."""
    user = update.effective_user
    with get_session() as s:
        u = get_or_create_user_by_tid(s, user.id)
        s.commit()

    text = (
        f"<b>👋 Welcome to Freelancer Alert Bot</b>\n\n"
        f"You have <b>{TRIAL_DAYS} days</b> free trial to explore job alerts.\n"
        "Use the buttons below to manage keywords, settings and alerts.\n\n"
        "<b>🔹 Features</b>\n"
        "• Instant job alerts from multiple freelance platforms\n"
        "• Keyword-based filtering for precision\n"
        "• Auto currency conversion to USD\n"
        "• Save and manage favourite jobs easily\n"
        "• Integrated admin & analytics dashboard\n"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(is_admin=is_admin_user(user.id)),
    )
    log.info("User %s started bot", user.id)
