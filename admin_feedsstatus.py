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

async def _feedsstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id if update.effective_user else None):
        return

    s: Dict[str, Any] = read_stats()
    feeds: Dict[str, Any] = s.get("feeds", {})
    if not feeds:
        await update.effective_chat.send_message(
            "No feed snapshot yet. Worker may be starting up."
        )
        return

    lines = []
    lines.append("🩺 *Feeds health (last cycle)*")
    cs = s.get("cycle_seconds")
    if cs:
        lines.append(f"_cycle duration_: `{cs}s`")
    lines.append("")

    for name, data in sorted(feeds.items()):
        cnt = data.get("count") or 0
        err = data.get("error")
        if err:
            lines.append(f"• `{name}` → {cnt} ⚠️ `{err}`")
        else:
            lines.append(f"• `{name}` → {cnt} ✅")

    await update.effective_chat.send_message("\n".join(lines), parse_mode="Markdown")

def register_feedsstatus(app: Application) -> None:
    app.add_handler(CommandHandler("feedsstatus", _feedsstatus_cmd))
