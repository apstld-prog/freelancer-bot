import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger("handlers.help")


def help_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back", callback_data="back_start")]
    ])


HELP_TEXT = (
    "👋 *How the bot works*\n\n"
    "This bot monitors multiple freelance platforms and sends you instant alerts "
    "whenever new jobs match your keywords.\n\n"
    "✅ Add keywords in Settings\n"
    "✅ The workers constantly scan: Freelancer, PPH, Skywalker, CareerJet, Kariera\n"
    "✅ You receive affiliate-safe links\n\n"
    "Use the buttons below to navigate."
)


async def help_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    await query.edit_message_text(
        HELP_TEXT,
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=help_menu()
    )

