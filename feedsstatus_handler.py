# feedsstatus_handler.py
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

FEED_ENV_KEYS = [
    "ENABLE_FREELANCER",
    "ENABLE_PPH",
    "ENABLE_KARIERA",
    "ENABLE_JOBFIND",
    "ENABLE_TWAGO",
    "ENABLE_FREELANCERMAP",
    "ENABLE_YUNOJUNO",
    "ENABLE_WORKSOME",
    "ENABLE_CODEABLE",
    "ENABLE_GURU",
    "ENABLE_99DESIGNS",
]

def _format_feeds_status() -> str:
    lines = ["Feeds:"]
    for k in FEED_ENV_KEYS:
        v = os.getenv(k, "0")
        lines.append(f"{k}={v}")
    return "\n".join(lines)

async def _feedsstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    admin_id = os.getenv("ADMIN_TELEGRAM_ID", "")
    if not update.effective_user:
        return
    if str(update.effective_user.id) != str(admin_id):
        await update.effective_chat.send_message("Admin only.")
        return
    await update.effective_chat.send_message(_format_feeds_status())

def register_feedsstatus_handler(app: Application) -> None:
    app.add_handler(CommandHandler("feedsstatus", _feedsstatus_cmd))
