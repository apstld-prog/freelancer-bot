# feedsstatus_handler.py
from __future__ import annotations
import os
from typing import Dict, Any
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

ADMIN_ID = os.getenv("ADMIN_TELEGRAM_ID")

# In-memory snapshot filled by the worker via worker_stats_sidecar.publish_stats
_LAST_STATS: Dict[str, Any] = {
    "feeds": {},              # {"freelancer":{"count":12,"error":None}, ...}
    "cycle_seconds": None,    # float
    "sent_this_cycle": 0,     # int
}

def _format_stats() -> str:
    if not _LAST_STATS["feeds"]:
        return "No stats yet."
    lines = ["*Feeds:*"]
    for name, data in sorted(_LAST_STATS["feeds"].items()):
        count = data.get("count", 0)
        err = data.get("error")
        if err:
            lines.append(f"• `{name}` = *{count}* _(error: {err})_")
        else:
            lines.append(f"• `{name}` = *{count}*")
    cs = _LAST_STATS.get("cycle_seconds")
    sent = _LAST_STATS.get("sent_this_cycle", 0)
    if cs is not None:
        lines.append(f"\nCycle: *{cs:.2f}s*, sent: *{sent}*")
    return "\n".join(lines)

async def _feedsstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not ADMIN_ID or str(update.effective_user.id) != str(ADMIN_ID):
        await update.effective_message.reply_text("Admin only.")
        return
    await update.effective_message.reply_markdown(_format_stats())

def register_feedsstatus_handler(app: Application) -> None:
    app.add_handler(CommandHandler("feedsstatus", _feedsstatus_cmd))

def _ingest(stats: Dict[str, Any]) -> None:
    # Called by worker_stats_sidecar.publish_stats (cross-module import)
    _LAST_STATS["feeds"] = stats.get("feeds_counts", {})
    _LAST_STATS["cycle_seconds"] = stats.get("cycle_seconds")
    _LAST_STATS["sent_this_cycle"] = stats.get("sent_this_cycle", 0)
