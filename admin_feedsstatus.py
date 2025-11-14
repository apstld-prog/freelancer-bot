# admin_feedsstatus.py
from __future__ import annotations
import os
from typing import Optional, Dict, Any

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, Application

from feedstats import read_stats

def _is_admin(tg_user_id: Optional[int]) -> bool:
    admin_env = os.getenv("ADMIN_ID") or os.getenv("TELEGRAM_ADMIN_ID")
    if not admin_env or tg_user_id is None:
        return False
    try:
        return int(admin_env) == int(tg_user_id)
    except Exception:
        return False

def _format_stats() -> str:
    s: Dict[str, Any] = read_stats()
    feeds: Dict[str, Any] = s.get("feeds", {})
    if not feeds:
        # Fallback μήνυμα αν δεν έχει γραφτεί ακόμα snapshot
        lines = [
            "🩺 *Feeds health*",
            "_No snapshot yet — worker may be starting up._",
        ]
        return "\n".join(lines)

    lines = []
    lines.append("🩺 *Feeds health (last cycle)*")
    cs = s.get("cycle_seconds")
    sent = s.get("sent_this_cycle", 0)
    meta = []
    if cs:   meta.append(f"⏱ `{cs}s`")
    meta.append(f"📨 sent: `{sent}`")
    lines.append(" ".join(meta))
    lines.append("")

    for name, data in sorted(feeds.items()):
        cnt = data.get("count") or 0
        err = data.get("error")
        if err:
            lines.append(f"• `{name}` → {cnt}  ⚠️ `{err}`")
        else:
            lines.append(f"• `{name}` → {cnt}  ✅")

    return "\n".join(lines)

async def _feedsstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id if update.effective_user else None):
        return
    await update.effective_chat.send_message(_format_stats(), parse_mode="Markdown")

def register_feedsstatus(app: Application) -> None:
    app.add_handler(CommandHandler("feedsstatus", _feedsstatus_cmd))
