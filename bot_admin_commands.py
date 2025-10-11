
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_IDS, STATS_WINDOW_HOURS
from db_events import get_platform_stats

async def cmd_feedstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    hours = STATS_WINDOW_HOURS
    stats = get_platform_stats(hours)
    if not stats:
        await update.effective_chat.send_message(f"No events in last {hours}h.")
        return
    lines = [f"📊 Feed status (last {hours}h):"]
    for src, cnt in stats.items():
        lines.append(f"• {src}: {cnt}")
    await update.effective_chat.send_message("\n".join(lines))
