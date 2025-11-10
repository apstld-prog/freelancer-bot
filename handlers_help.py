from telegram import Update
from telegram.ext import ContextTypes

async def help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "*Help Menu*\n"
        "________________________________________\n"
        "â€¢ Add keywords to receive matching jobs.\n"
        "â€¢ Jobs are scanned every few minutes.\n"
        "â€¢ Use Settings to manage your alerts.\n"
        "â€¢ Use /start to return to the main menu.\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

