# worker_runner.py
import os
import time
import logging
import hashlib
import datetime as _dt
import asyncio
from typing import List, Dict, Tuple

from sqlalchemy import text
from db import get_session
from worker import run_pipeline                     # το υπάρχον pipeline σου
from config import FX_USD_RATES
from utils_fx import load_fx_rates, to_usd          # ισοτιμίες -> USD

# PTB (async) για να έχουμε ΙΔΙΟ UI (inline keyboard)
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode

log = logging.getLogger("worker")

# ---------------- relative time helpers ----------------
def _parse_timestamp(val):
    if val is None:
        return None
    try:
        if isinstance(val, (int, float)):
            return _dt.datetime.fromtimestamp(float(val), tz=_dt.timezone.utc)
        s = str(val).strip()
        try:
            dt = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_dt.timezone.utc)
            return dt.astimezone(_dt.timezone.utc)
        except Exception:
            pass
        if s.isdigit():
            return _dt.datetime.fromtimestamp(int(s), tz=_dt.timezone.utc)
    except Exception:
        return None
    return None

def _posted_ago(item: dict) -> str | None:
    if str(os.getenv("SHOW_RELATIVE_AGE", "on")).lower() in ("0", "off", "false", "no"):
        return None
    for key in ("posted_at", "created_at", "published_at", "date", "timestamp", "ts"):
        dt = _parse_timestamp(item.get(key))
        if dt:
            now = _dt.datetime.now(_dt.timezone.utc)
            sec = max(0, int((now - dt).total_seconds()))
            if sec < 60:
                return f"{sec}s ago"
            mins = sec // 60
            if mins < 60:
                return f"{mins}m ago"
            hrs = mins // 60
            if hrs < 24:
                return f"{hrs}h ago"
            days = hrs // 24
            return f"{days}d ago"
    return None

# ---------------- formatting helpers ----------------
def _job_key(it: Dict) -> str:
    k = it.get("job_key")
    if k:
        return k
    src = (it.get("original_url") or it.get("proposal_url") or it.get("affiliate_url") or it.get("title") or "")
    return hashlib.sha1(src.encode("utf-8", errors="ignore")).hexdigest()

def _first_url(it: Dict) -> str:
    for k in ("affiliate_url", "proposal_url", "original_url", "url"):
        u = (it.get(k) or "").strip()
        if u:
            return u
    return ""

def _fmt_amount(x):
    if x is None:
        return ""
    if isinstance(x, (int,)) or (isinstance(x, float) and x.is_integer()):
        return str(int(x))
    return f"{x:.2f}".rstrip("0").rstrip(".")

def _compose_budget_line(it: Dict, fx: Dict) -> str | None:
    cur = (it.get("currency") or "").upper()
    bmin, bmax = it.get("budget_min"), it.get("budget_max")
    if bmin is None and bmax is None:
        return None

    # Αν χρειάζεται, υπολόγισε USD εδώ (ακόμα κι αν δεν ήρθε από pipeline)
    umin = it.get("budget_min_usd")
    umax = it.get("budget_max_usd")
    if cur and cur != "USD":
        try:
            if bmin is not None and umin is None:
                umin = to_usd(bmin, cur, fx)
            if bmax is not None and umax is None:
                umax = to_usd(bmax, cur, fx)
        except Exception:
            pass

    # Native range
    if bmin is not None and bmax is not None:
        native = f"{_fmt_amount(bmin)}–{_fmt_amount(bmax)} {cur or 'USD'}"
    else:
        native = f"{_fmt_amount(bmin if bmin is not None else bmax)} {cur or 'USD'}"

    # USD part
    usd_part = ""
    if cur and cur != "USD" and (umin is not None or umax is not None):
        if umin is not None and umax is not None:
            usd_part = f" (~ {_fmt_amount(umin)}–{_fmt_amount(umax)} USD)"
        else:
            usd_part = f" (~ {_fmt_amount(umin if umin is not None else umax)} USD)"

    return f"💰 {native}{usd_part}"

def _compose_text(it: Dict, fx: Dict) -> str:
    parts: List[str] = []
    title = (it.get("title") or "").strip()
    if title:
        parts.append(f"<b>{title}</b>")

    # Budget first (όπως στο αρχικό UI)
    bline = _compose_budget_line(it, fx)
    if bline:
        parts.append(bline)

    # Description
    desc = (it.get("description") or "").strip()
    if desc:
        if len(desc) > 600:
            desc = desc[:600] + "…"
        parts.append(desc)

    # Match line
    if it.get("matched_keyword"):
        parts.append(f"Match: <b>{it['matched_keyword']}</b>")

    # Source tag (ίδιο στυλ)
    parts.append("🏷️ <i>freelancer</i>")

    # Posted relative
    age = _posted_ago(it)
    if age:
        parts.append(f"🕓 Posted: {age}")

    return "\n".join(parts)

def _action_keyboard(proposal_url: str, original_url: str) -> InlineKeyboardMarkup:
    """Ίδιο layout:
       [ Proposal | Original ]
       [ Save     | Delete   ]
    """
    row1 = [
        InlineKeyboardButton("📝 Proposal", url=proposal_url),
        InlineKeyboardButton("🔗 Original", url=original_url),
    ]
    row2 = [
        InlineKeyboardButton("⭐ Save", callback_data="job:save"),
        InlineKeyboardButton("🗑️ Delete", callback_data="job:delete"),
    ]
    return InlineKeyboardMarkup([row1, row2])

# ---------------- core runner ----------------
def _fetch_receivers(s) -> List[int]:
    u1 = s.execute(text('SELECT DISTINCT telegram_id FROM "user"  WHERE telegram_id IS NOT NULL AND COALESCE(is_blocked,false)=false AND COALESCE(is_active,true)=true')).fetchall()
    u2 = s.execute(text('SELECT DISTINCT telegram_id FROM users WHERE telegram_id IS NOT NULL AND COALESCE(is_blocked,false)=false')).fetchall()
    return sorted({int(r[0]) for r in u1} | {int(r[0]) for r in u2})

async def _send_one(bot: Bot, uid: int, text: str, kb: InlineKeyboardMarkup):
    await bot.send_message(
        chat_id=uid,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
        disable_web_page_preview=True,
    )

async def _run_async():
    s = get_session()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        log.error("Missing TELEGRAM_BOT_TOKEN")
        return

    bot = Bot(token=token)
    fx = load_fx_rates(FX_USD_RATES) or {}

    receivers = _fetch_receivers(s)
    log.info(f"[users] total receivers: {len(receivers)} (per-user keywords where available)")

    # φέρε items από το pipeline (match σε τίτλο + περιγραφή, enrich)
    items = run_pipeline([])

    sent = 0
    for it in items:
        try:
            key = _job_key(it)

            # de-dup per user
            for uid in receivers:
                try:
                    s.execute(
                        text("INSERT INTO sent_job (chat_id, job_key) VALUES (:u, :k) ON CONFLICT DO NOTHING;"),
                        {"u": uid, "k": key},
                    )
                    s.commit()
                except Exception:
                    s.rollback()
                    # συνεχίζουμε – αν υπάρχει ήδη, απλώς δεν ξαναστέλνουμε
                    continue

                text_msg = _compose_text(it, fx)
                prop = it.get("proposal_url") or _first_url(it)
                orig = it.get("original_url") or _first_url(it)
                kb = _action_keyboard(prop or orig, orig or prop)

                await _send_one(bot, uid, text_msg, kb)
                sent += 1
                await asyncio.sleep(0.2)
        except Exception as e:
            log.warning("compose/send skipped due to error: %s", e)

    log.info(f"[runner] sent {sent} messages")

def run_worker():
    asyncio.run(_run_async())

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:worker:%(message)s")
    run_worker()
