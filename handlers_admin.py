import logging
from telegram import Update
from telegram.ext import ContextTypes

from config import ADMIN_IDS
from db_events import get_platform_stats

log = logging.getLogger("handlers_admin")


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if uid not in ADMIN_IDS:
        await update.message.reply_text("Access denied.")
        return

    stats = get_platform_stats()

    lines = ["*Platform Stats (last 24h)*", "________________________________________"]
    for p, count in stats.items():
        lines.append(f"Ã¢â‚¬Â¢ {p}: {count}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


