import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from utils import get_keywords, add_keyword, remove_keyword, get_or_create_user

logger = logging.getLogger("handlers.ui")


def ui_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Add Keyword", callback_data="add_kw"),
            InlineKeyboardButton("➖ Remove Keyword", callback_data="remove_kw"),
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_start")],
    ])


async def ui_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_or_create_user(update)
    keywords = get_keywords(user.id)

    text = "🟩 *Your Keywords*\n\n"
    if not keywords:
        text += "_No keywords yet._\n"
    else:
        for kw in keywords:
            text += f"• `{kw}`\n"

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=text,
            parse_mode="Markdown",
            reply_markup=ui_menu()
        )
    else:
        await update.message.reply_text(
            text=text,
            parse_mode="Markdown",
            reply_markup=ui_menu()
        )


async def add_keyword_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text(
        "Send me the keyword you want to add:",
        parse_mode="Markdown"
    )
    context.user_data["awaiting_kw_add"] = True


async def remove_keyword_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text(
        "Send me the keyword you want to remove:",
        parse_mode="Markdown"
    )
    context.user_data["awaiting_kw_remove"] = True


async def process_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_or_create_user(update)

    if context.user_data.get("awaiting_kw_add"):
        kw = update.message.text.strip()
        add_keyword(user.id, kw)
        context.user_data["awaiting_kw_add"] = False
        await update.message.reply_text(f"✅ Added keyword: `{kw}`", parse_mode="Markdown")
        return

    if context.user_data.get("awaiting_kw_remove"):
        kw = update.message.text.strip()
        removed = remove_keyword(user.id, kw)
        context.user_data["awaiting_kw_remove"] = False

        if removed:
            await update.message.reply_text(f"✅ Removed keyword: `{kw}`", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"⚠️ Keyword not found: `{kw}`", parse_mode="Markdown")
        return

