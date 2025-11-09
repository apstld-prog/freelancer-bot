import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from utils import get_or_create_user

log = logging.getLogger("handlers_ui")


# ---------------------------------------------------------
# MAIN UI ROUTER (CallbackQuery)
# ---------------------------------------------------------
async def handle_ui_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    # MAIN MENU BACK
    if data == "ui:back_main":
        await show_main_menu(update, context)
        return

    # SETTINGS
    if data == "ui:settings":
        await show_settings_menu(update, context)
        return

    # KEYWORDS MENU
    if data == "ui:keywords":
        await show_keywords_menu(update, context)
        return

    # Unknown
    await query.edit_message_text("Unknown action.")


# ---------------------------------------------------------
# MAIN MENU SCREEN
# ---------------------------------------------------------
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_or_create_user(user.id)

    text = (
        "👋 Welcome to Freelancer Alert Bot!\n\n"
        "Use the menu below."
    )

    keyboard = [
        [
            InlineKeyboardButton("🟩 Keywords", callback_data="ui:keywords"),
            InlineKeyboardButton("⚙️ Settings", callback_data="ui:settings")
        ]
    ]

    await update.callback_query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ---------------------------------------------------------
# SETTINGS MENU
# ---------------------------------------------------------
async def show_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "⚙️ **Settings**\n\nSelect an option."

    keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="ui:back_main")]]

    await update.callback_query.edit_message_text(
        text=text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ---------------------------------------------------------
# KEYWORDS MENU (STATIC PLACEHOLDER)
# ---------------------------------------------------------
async def show_keywords_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "🟩 **Your Keywords**\n\nKeyword management will be added soon."

    keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="ui:back_main")]]

    await update.callback_query.edit_message_text(
        text=text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ---------------------------------------------------------
# MESSAGE HANDLER FOR FALLBACK
# ---------------------------------------------------------
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Please use the buttons below the messages."
    )

