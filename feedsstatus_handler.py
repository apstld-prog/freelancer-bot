# feedsstatus_handler.py
# Admin-only /feedsstatus με κουμπί 🔄 Refresh.
# Διαβάζει τα τελευταία στατιστικά του worker από τον πίνακα WorkerStat.
# Αν δεν υπάρχει πίνακας/εγγραφή, πέφτει σε ασφαλές fallback.

from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
)

# --- Προσπαθούμε να διαβάσουμε από τη ΒΔ (optional) ---
# Περιμένουμε να υπάρχει get_session() και WorkerStat στον db.py.
# Αν δεν υπάρχουν, θα δουλέψει με fallback.
try:
    from db import get_session  # type: ignore
    from db import WorkerStat   # type: ignore
except Exception:  # pragma: no cover
    get_session = None
    WorkerStat = None  # type: ignore


ADMIN_TG_ID = os.getenv("ADMIN_TG_ID", "").strip()  # π.χ. "5254014824"


# ---------- Helpers ----------

def _is_admin(update: Update) -> bool:
    if not ADMIN_TG_ID:
        return False
    eff_user = update.effective_user
    return bool(eff_user and str(eff_user.id) == ADMIN_TG_ID)


def _fmt_bool(b: bool) -> str:
    return "✅" if b else "⚠️"


def _fmt_age(ts: Optional[datetime]) -> str:
    if not ts:
        return "—"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    sec = max(0, int((now - ts).total_seconds()))
    if sec < 60:
        return f"{sec}s ago"
    mins = sec // 60
    if mins < 60:
        return f"{mins}m ago"
    hrs = mins // 60
    return f"{hrs}h ago"


def _format_stats_text(data: Dict[str, Any]) -> str:
    """
    Αναμένει dict:
    {
      "cycle_seconds": 120,
      "sent_this_cycle": 3,
      "feeds_counts": {
         "freelancer": {"count": 12, "error": null},
         "pph": {"count": 0, "error": "HTTP 403"}
      },
      "ts": "... ISO ..."
    }
    """
    cycle = data.get("cycle_seconds", "—")
    sent = data.get("sent_this_cycle", "—")
    feeds: Dict[str, Dict[str, Any]] = data.get("feeds_counts", {}) or {}

    ts_str = data.get("ts")
    ts: Optional[datetime] = None
    if ts_str:
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except Exception:
            ts = None

    lines = []
    lines.append("🩺 *Feeds health*")
    lines.append(f"⏱ `{cycle}s`   📨 sent: *{sent}*")
    lines.append(f"_updated: { _fmt_age(ts) }_")
    lines.append("")

    if not feeds:
        lines.append("No feed data yet.")
    else:
        for name, rec in feeds.items():
            cnt = rec.get("count", 0)
            err = rec.get("error")
            ok = err in (None, "", "OK")
            err_disp = "—" if not err else str(err)
            lines.append(f"• *{name}* — *{cnt}* {_fmt_bool(ok)} `{err_disp}`")

    return "\n".join(lines)


def _keyboard_refresh() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔄 Refresh", callback_data="feedsstatus_refresh")]]
    )


# ---------- DB access ----------

def _load_latest_stats_from_db() -> Optional[Dict[str, Any]]:
    """Δοκιμάζει να διαβάσει το τελευταίο snapshot από WorkerStat."""
    if not get_session or not WorkerStat:
        return None
    try:
        with get_session() as db:
            row = (
                db.query(WorkerStat)
                .order_by(WorkerStat.id.desc())
                .limit(1)
                .one_or_none()
            )
            if not row:
                return None
            # Περιμένουμε JSON πεδίο 'payload' με το schema που περιγράφεται στο _format_stats_text
            payload = row.payload if hasattr(row, "payload") else None
            if not payload:
                return None
            if isinstance(payload, str):
                data = json.loads(payload)
            else:
                data = dict(payload)
            # σιγουρευόμαστε ότι υπάρχει timestamp
            if "ts" not in data:
                data["ts"] = row.created_at.isoformat() if hasattr(row, "created_at") else None
            return data
    except Exception:
        return None


def _fallback_stats_from_env() -> Dict[str, Any]:
    """
    Fallback: διαβάζουμε ENABLE_* από env για να δώσουμε έστω μια εικόνα.
    Δεν εξαρτάται από DB.
    """
    feeds = [
        "FREELANCER",
        "PPH",
        "KARIERA",
        "JOBFIND",
        "TWAGO",
        "FREELANCERMAP",
        "YUNOJUNO",
        "WORKSOME",
        "CODEABLE",
        "GURU",
        "99DESIGNS",
    ]
    feeds_counts = {}
    for f in feeds:
        v = os.getenv(f"ENABLE_{f}", "0").strip()
        enabled = (v == "1")
        feeds_counts[f.lower()] = {"count": 0 if enabled else 0, "error": None if enabled else "disabled"}
    return {
        "cycle_seconds": int(os.getenv("WORKER_INTERVAL", "120")),
        "sent_this_cycle": 0,
        "feeds_counts": feeds_counts,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def _get_stats_payload() -> Dict[str, Any]:
    data = _load_latest_stats_from_db()
    if data:
        return data
    return _fallback_stats_from_env()


# ---------- Handlers ----------

async def _feedsstatus_core(update: Update, context: ContextTypes.DEFAULT_TYPE, edit_message: bool) -> None:
    if not _is_admin(update):
        # σιωπηλή άρνηση για μη-admin
        return

    payload = _get_stats_payload()
    text = _format_stats_text(payload)
    kb = _keyboard_refresh()

    if edit_message and update.callback_query and update.callback_query.message:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(
            text, parse_mode="Markdown", reply_markup=kb, disable_web_page_preview=True
        )
    else:
        target = update.effective_message
        if target:
            await target.reply_text(
                text, parse_mode="Markdown", reply_markup=kb, disable_web_page_preview=True
            )


async def feedsstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _feedsstatus_core(update, context, edit_message=False)


async def feedsstatus_refresh_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _feedsstatus_core(update, context, edit_message=True)


def register_feedsstatus_handler(app: Application) -> None:
    """
    Κάλεσέ το μία φορά στο build_application():
        from feedsstatus_handler import register_feedsstatus_handler
        ...
        register_feedsstatus_handler(app)
    """
    app.add_handler(CommandHandler("feedsstatus", feedsstatus_cmd))
    app.add_handler(CallbackQueryHandler(feedsstatus_refresh_cb, pattern="^feedsstatus_refresh$"))
