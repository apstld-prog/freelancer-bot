import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from utils import get_or_create_user_by_tid

log = logging.getLogger("handlers_start")


START_MESSAGE = (
    "👋 *Welcome to Freelancer Alert Bot!*\n"
    "🎁 You have a 10-day free trial.\n"
    "Automatically finds matching freelance jobs from top platforms and sends you instant alerts with affiliate-safe links.\n"
    "Use /help to see how it works.\n"
    "________________________________________\n"
    "🟩 *Keywords*  ⚙️ *Settings*\n"
    "📘 *Help*  💾 *Saved*\n"
    "📞 *Contact*\n"
    "🔥 *Admin*\n"
    "________________________________________\n"
    "✨ *Features*\n"
    "• Realtime job alerts (Freelancer API)\n"
    "• Affiliate-wrapped Proposal & Original links\n"
    "• Budget shown + USD conversion\n"
    "• ⭐ Keep / 🗑️ Delete buttons\n"
    "• 10-day free trial, extend via admin\n"
    "• Multi-keyword search (single/all modes)\n"
    "• Platforms by country (incl. GR boards)"
)


def main_menu_keyboard(is_admin: bool) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("🟩 Keywords", callback_data="ui:keywords"),
            InlineKeyboardButton("⚙️ Settings", callback_data="ui:settings"),
        ],
        [
            InlineKeyboardButton("📘 Help", callback_data="ui:help"),
            InlineKeyboardButton("💾 Saved", callback_data="ui:saved"),
        ],
        [
            InlineKeyboardButton("📞 Contact", callback_data="ui:contact"),
        ]
    ]

    if is_admin:
        buttons.append([InlineKeyboardButton("🔥 Admin", callback_data="ui:admin")])

    return InlineKeyboardMarkup(buttons)



async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /start correctly in webhook mode."""
    try:
        user = update.effective_user
        tid = user.id

        # DB ensure
        get_or_create_user_by_tid(tid)

        # Load admin list from env -> bot_data
        admin_ids = context.bot_data.get("ADMIN_IDS", [])
        is_admin = tid in admin_ids

        keyboard = main_menu_keyboard(is_admin)

        # If webhook sends update without message
        if update.message:
            await update.message.reply_markdown(START_MESSAGE, reply_markup=keyboard)
        else:
            await context.bot.send_message(tid, START_MESSAGE, reply_markup=keyboard)

    except Exception as e:
        log.error(f"/start error: {e}", exc_info=True)
