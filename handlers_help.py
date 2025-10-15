
from telegram import Update
from telegram.ext import ContextTypes
from ui_texts import HELP_EN, help_footer
from config import STATS_WINDOW_HOURS

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = HELP_EN + help_footer(hours=STATS_WINDOW_HOURS)
    await update.effective_chat.send_message(text, parse_mode="HTML")
