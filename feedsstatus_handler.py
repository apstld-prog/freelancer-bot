from __future__ import annotations
import os
from typing import List

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from worker_stats_sidecar import read_last_cycle_stats

ADMIN_TG_ID = os.getenv("ADMIN_TG_ID", "")

FEED_FLAGS = [
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

def _enabled_text(v: str | None) -> str:
    return "1" if (v is not None and v.strip() not in ("0", "", "false", "False")) else "0"

async def feedsstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_TG_ID):
        await update.effective_chat.send_message("Admin only.")
        return

    lines: List[str] = ["<b>Feeds:</b>"]
    for key in FEED_FLAGS:
        lines.append(f"{key}={_enabled_text(os.getenv(key))}")

    stats = read_last_cycle_stats()
    if stats:
        sent = stats.get("sent_this_cycle", 0)
        sec = stats.get("cycle_seconds", 0)
        lines.append("")
        lines.append(f"<b>Last worker cycle:</b> sent={sent}, duration={int(sec)}s")
        feeds_counts = stats.get("feeds_counts") or {}
        for feed, row in feeds_counts.items():
            cnt = row.get("count", 0)
            err = row.get("error")
            if err:
                lines.append(f"• {feed}: {cnt} (err: {err})")
            else:
                lines.append(f"• {feed}: {cnt}")

    await update.effective_chat.send_message("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)

def register_feedsstatus_handler(app: Application) -> None:
    app.add_handler(CommandHandler("feedsstatus", feedsstatus_cmd))
