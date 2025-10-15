from telegram import Update
from telegram.ext import ContextTypes

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles /help command — shows user guidance for all main commands.
    """
    text = (
        "ℹ️ *Freelancer Alert Bot — Help*\n\n"
        "/start — Start the bot and see welcome message\n"
        "/feedstatus — Show current feed and keyword setup\n"
        "/selftest — Run diagnostic test (for admin use)\n"
        "/help — Show this help message\n\n"
        "💡 Tip: When a job appears, use the ⭐ Save button to store it in your saved list."
    )
    await update.message.reply_text(text, parse_mode="Markdown")
