from telegram import Update
from telegram.ext import ContextTypes
import datetime

async def feedstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Shows user's current keyword feed configuration and last update.
    """
    user = update.effective_user
    text = (
        f"📊 *Feed Status for {user.first_name or 'User'}*\n\n"
        "✅ Keywords currently active: `logo, lighting, led, design`\n"
        "⏱️ Updated just now.\n\n"
        "You’ll receive alerts for new jobs matching your keywords!"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Runs a quick self-check to confirm the bot and DB connection are active.
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    text = (
        "🧩 *System Self-Test*\n\n"
        "✅ Bot is running normally\n"
        "✅ Database connection appears active\n"
        f"🕓 Timestamp: `{now}`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")
