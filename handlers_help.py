from telegram import Update
from telegram.ext import ContextTypes

async def help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "*Help Menu*\n"
        "________________________________________\n"
        "• Add keywords to receive matching jobs.\n"
        "• Jobs are scanned every few minutes.\n"
        "• Use Settings to manage your alerts.\n"
        "• Use /start to return to the main menu.\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")
