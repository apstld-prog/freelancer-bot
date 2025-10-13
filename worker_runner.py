import os
import time
import logging
import datetime as _dt
from telegram import Bot
from telegram.constants import ParseMode
from sqlalchemy import text
from db import get_session
from platform_freelancer import fetch_freelancer_jobs

log = logging.getLogger("worker")

# ---- time helpers (relative "Posted: 1m/2h/3d") ----
def _parse_timestamp(val):
    if val is None:
        return None
    try:
        # epoch seconds
        if isinstance(val, (int, float)):
            return _dt.datetime.fromtimestamp(float(val), tz=_dt.timezone.utc)
        s = str(val).strip()
        # ISO 8601
        try:
            dt = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_dt.timezone.utc)
            return dt.astimezone(_dt.timezone.utc)
        except Exception:
            pass
        # numeric string epoch
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
            sec = int((now - dt).total_seconds())
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

# ---- compose message ----
def _compose_message(job: dict) -> str:
    lines = []
    title = job.get("title", "").strip()
    if title:
        lines.append(f"💼 <b>{title}</b>")

    if job.get("description"):
        desc = job["description"].strip()
        if len(desc) > 300:
            desc = desc[:300] + "..."
        lines.append(desc)

    # price + conversion
    budget = job.get("budget_amount")
    cur = job.get("budget_currency", "")
    usd = job.get("budget_usd")
    if budget:
        if cur and usd and cur.upper() != "USD":
            lines.append(f"💰 {budget} {cur.upper()} (~{usd} USD)")
        else:
            lines.append(f"💰 {budget} {cur.upper() or 'USD'}")

    # keyword match
    if job.get("matched_keyword"):
        lines.append(f"🔎 Match: <b>{job['matched_keyword']}</b>")

    # posted ago
    age = _posted_ago(job)
    if age:
        lines.append(f"🕓 Posted: {age}")

    if job.get("url"):
        lines.append(f"\n🔗 <a href=\"{job['url']}\">View details</a>")

    return "\n".join(lines)

# ---- runner main ----
def run_worker():
    s = get_session()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        log.error("Missing TELEGRAM_BOT_TOKEN")
        return
    bot = Bot(token=token)

    # get all active user ids
    u1 = s.execute(text('SELECT DISTINCT telegram_id FROM "user" WHERE telegram_id IS NOT NULL AND COALESCE(is_blocked,false)=false AND COALESCE(is_active,true)=true')).fetchall()
    u2 = s.execute(text('SELECT DISTINCT telegram_id FROM users WHERE telegram_id IS NOT NULL AND COALESCE(is_blocked,false)=false')).fetchall()
    receivers = sorted({int(r[0]) for r in u1} | {int(r[0]) for r in u2})
    log.info(f"[users] total receivers: {len(receivers)} (per-user keywords where available)")

    jobs = fetch_freelancer_jobs()
    sent = 0

    for job in jobs:
        msg = _compose_message(job)
        key = job.get("job_key")
        for uid in receivers:
            try:
                s.execute(text("INSERT INTO sent_job (chat_id, job_key) VALUES (:u, :k) ON CONFLICT DO NOTHING;"), {"u": uid, "k": key})
                s.commit()
                bot.send_message(chat_id=uid, text=msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                time.sleep(1)
                sent += 1
            except Exception as e:
                s.rollback()
                log.warning(f"send_message failed for {uid}: {e}")

    log.info(f"[runner] sent {sent} messages")

if __name__ == "__main__":
    run_worker()
