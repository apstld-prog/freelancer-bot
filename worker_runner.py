# worker_runner.py
import os
import time
import json
import hashlib
import logging
import datetime as _dt
import requests
from sqlalchemy import text
from db import get_session
from worker import run_pipeline  # use the working pipeline

log = logging.getLogger("worker")

# ---------------- time helpers (relative "Posted: 1m/2h/3d") ----------------
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
    # disable if SHOW_RELATIVE_AGE=off
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

# ---------------- utils ----------------
def _first_url(it: dict) -> str:
    for k in ("affiliate_url", "proposal_url", "original_url", "url"):
        u = (it.get(k) or "").strip()
        if u:
            return u
    return ""

def _job_key(it: dict) -> str:
    # use existing if present, else hash url/title
    k = it.get("job_key")
    if k:
        return k
    src = (it.get("original_url") or it.get("proposal_url") or it.get("affiliate_url") or it.get("title") or "")
    return hashlib.sha1(src.encode("utf-8", errors="ignore")).hexdigest()

def _fmt_amount(x):
    if x is None:
        return ""
    if isinstance(x, (int,)) or (isinstance(x, float) and x.is_integer()):
        return str(int(x))
    return f"{x}"

def _compose_budget_lines(it: dict) -> list[str]:
    lines = []
    cur = (it.get("currency") or "").upper()
    bmin, bmax = it.get("budget_min"), it.get("budget_max")
    umin, umax = it.get("budget_min_usd"), it.get("budget_max_usd")

    has_native = (bmin is not None) or (bmax is not None)
    has_usd = (umin is not None) or (umax is not None)

    if not has_native and not has_usd:
        return lines

    if has_native:
        if bmin is not None and bmax is not None:
            native = f"{_fmt_amount(bmin)}–{_fmt_amount(bmax)} {cur or 'USD'}"
        else:
            native = f"{_fmt_amount(bmin if bmin is not None else bmax)} {cur or 'USD'}"
    else:
        native = ""

    usd_str = ""
    if cur and cur != "USD" and has_usd:
        if umin is not None and umax is not None:
            usd_str = f" (~ {_fmt_amount(umin)}–{_fmt_amount(umax)} USD)"
        else:
            usd_str = f" (~ {_fmt_amount(umin if umin is not None else umax)} USD)"

    if native or usd_str:
        lines.append(f"💰 {native}{usd_str}")
    return lines

def _compose_message(it: dict) -> str:
    lines = []
    title = (it.get("title") or "").strip()
    if title:
        lines.append(f"💼 <b>{title}</b>")

    desc = (it.get("description") or "").strip()
    if desc:
        if len(desc) > 300:
            desc = desc[:300] + "..."
        lines.append(desc)

    lines += _compose_budget_lines(it)

    if it.get("matched_keyword"):
        lines.append(f"🔎 Match: <b>{it['matched_keyword']}</b>")

    age = _posted_ago(it)
    if age:
        lines.append(f"🕓 Posted: {age}")

    url = _first_url(it)
    if url:
        lines.append(f"\n🔗 <a href=\"{url}\">View details</a>")

    return "\n".join(lines)

def _send_telegram(token: str, chat_id: int, text: str):
    api = os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org").rstrip("/")
    url = f"{api}/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code != 200:
            log.warning("send_message failed [%s]: %s", r.status_code, r.text[:200])
    except Exception as e:
        log.warning("send_message exception: %s", e)

# ---------------- runner main ----------------
def run_worker():
    s = get_session()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        log.error("Missing TELEGRAM_BOT_TOKEN")
        return

    # receivers (both tables)
    u1 = s.execute(text('SELECT DISTINCT telegram_id FROM "user"  WHERE telegram_id IS NOT NULL AND COALESCE(is_blocked,false)=false AND COALESCE(is_active,true)=true')).fetchall()
    u2 = s.execute(text('SELECT DISTINCT telegram_id FROM users WHERE telegram_id IS NOT NULL AND COALESCE(is_blocked,false)=false')).fetchall()
    receivers = sorted({int(r[0]) for r in u1} | {int(r[0]) for r in u2})
    log.info(f"[users] total receivers: {len(receivers)} (per-user keywords where available)")

    # fetch items via pipeline (title+description filtered & enriched)
    jobs = run_pipeline([])  # keep [] -> pipeline handles keyword matching internally
    sent = 0

    for it in jobs:
        try:
            key = _job_key(it)
            msg = _compose_message(it)
            # de-dup per user
            for uid in receivers:
                try:
                    s.execute(text("INSERT INTO sent_job (chat_id, job_key) VALUES (:u, :k) ON CONFLICT DO NOTHING;"),
                              {"u": uid, "k": key})
                    s.commit()
                    _send_telegram(token, uid, msg)
                    time.sleep(0.3)
                    sent += 1
                except Exception as e:
                    s.rollback()
                    log.warning("send_message failed for %s: %s", uid, e)
        except Exception as e:
            log.warning("compose/send skipped due to error: %s", e)

    log.info(f"[runner] sent {sent} messages")

if __name__ == "__main__":
    log.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s:worker:%(message)s"))
    log.addHandler(handler)
    run_worker()
