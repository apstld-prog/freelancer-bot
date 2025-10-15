from telegram import Update
from telegram.ext import ContextTypes

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the /start command for Freelancer Alert Bot.
    Welcomes the user and provides basic guidance.
    """
    user = update.effective_user
    text = (
        f"👋 Hello {user.first_name or 'there'}!\n\n"
        "Welcome to *Freelancer Alert Bot* 🚀\n\n"
        "This bot sends you fresh freelance job listings that match your keywords.\n"
        "Use /feedstatus to view your current feed setup.\n"
        "Use /help for available commands.\n\n"
        "Happy freelancing! 💼"
    )
    await update.message.reply_text(text, parse_mode="Markdown")
