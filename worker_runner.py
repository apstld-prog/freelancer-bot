import os
import time
import html
import logging
import asyncio
from datetime import datetime, timezone, timedelta

import httpx
import psycopg2

from platform_freelancer import fetch_freelancer_jobs
from platform_peopleperhour import fetch_pph_jobs
from platform_skywalker import fetch_skywalker_jobs

log = logging.getLogger("worker")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

DB_URL = os.getenv("DATABASE_URL")
BOT_TOKEN = (
    os.getenv("BOT_TOKEN")
    or os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
)
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "180"))
MAX_SEND = int(os.getenv("WORKER_MAX_SEND", "10"))
MAX_AGE_HOURS = 48

def get_connection():
    return psycopg2.connect(DB_URL)

def fetch_users():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT telegram_id, keywords FROM "user"')
            return cur.fetchall()

def parse_iso(dt_str):
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(str(dt_str).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def fmt_timeago(dt):
    if not dt:
        return ""
    now = datetime.now(timezone.utc)
    diff = now - dt
    if diff < timedelta(minutes=1):
        return "just now"
    m = int(diff.total_seconds() // 60)
    if m < 60:
        return f"{m}m ago"
    h = int(m // 60)
    if h < 24:
        return f"{h}h ago"
    d = int(h // 24)
    return f"{d}d ago"

def within_age(dt, hours):
    if not dt:
        return True
    return (datetime.now(timezone.utc) - dt) <= timedelta(hours=hours)

def pick_url(job: dict):
    original = job.get("original_url") or job.get("url") or job.get("link")
    proposal = job.get("affiliate_url") or job.get("proposal_url") or original
    return proposal, original

def _fmt_money(v):
    if v is None:
        return None
    try:
        n = float(v)
        return f"{int(n)}" if abs(n - round(n)) < 1e-9 else f"{n:.2f}"
    except Exception:
        return str(v)

def build_budget_line(job: dict) -> str:
    cur = (job.get("budget_currency") or job.get("currency") or "").upper()
    minv = job.get("budget_min")
    maxv = job.get("budget_max")
    one  = job.get("budget_amount")
    usd_min = job.get("usd_min")
    usd_max = job.get("usd_max")
    usd_one = job.get("usd_amount")

    if minv is not None or maxv is not None:
        local = f"{_fmt_money(minv)}–{_fmt_money(maxv)} {cur}".strip() if cur else f"{_fmt_money(minv)}–{_fmt_money(maxv)}"
        if usd_min is not None or usd_max is not None:
            usd = f"${_fmt_money(usd_min)}–${_fmt_money(usd_max)} USD"
            return f"{local} ({usd})"
        return local

    if one is not None:
        local = f"{_fmt_money(one)} {cur}".strip() if cur else _fmt_money(one)
        if usd_one is not None:
            usd = f"${_fmt_money(usd_one)} USD"
            return f"{local} ({usd})"
        return local

    return "N/A"

def safe_html(s: str | None) -> str:
    return html.escape(s or "")

async def send_job(bot_token: str, chat_id: int, job: dict):
    title = safe_html(job.get("title") or "Untitled")
    source = safe_html(job.get("source") or "")
    match_kw = safe_html(job.get("match") or "")
    desc = safe_html((job.get("description") or "").strip())
    if len(desc) > 350:
        desc = desc[:347].rsplit(" ", 1)[0] + "…"

    posted_at = parse_iso(job.get("posted_at"))
    if not within_age(posted_at, MAX_AGE_HOURS):
        return

    time_line = fmt_timeago(posted_at)
    budget_line = build_budget_line(job)

    rows = [
        f"<b>{title}</b>",
        f"<b>Budget:</b> {safe_html(budget_line)}",
        f"<b>Source:</b> {source}" if source else None,
        f"<b>Match:</b> {match_kw}" if match_kw else None,
        desc if desc else None,
        f"<i>{time_line}</i>" if time_line else None,
    ]
    text = "\n".join([r for r in rows if r])

    proposal_url, original_url = pick_url(job)
    kb1 = []
    if proposal_url:
        kb1.append({"text": "📄 Proposal", "url": proposal_url})
    if original_url:
        kb1.append({"text": "🔗 Original", "url": original_url})
    kb2 = [{"text": "⭐ Save", "callback_data": "job:save"},
           {"text": "🗑️ Delete", "callback_data": "job:delete"}]
    reply_markup = {"inline_keyboard": [kb1, kb2]} if kb1 else {"inline_keyboard": [kb2]}

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": reply_markup,
    }

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json=payload)
        if r.status_code != 200:
            log.warning(f"send_job error {r.status_code}: {r.text}")

async def ensure_awaitable(x):
    if asyncio.iscoroutine(x):
        return await x
    return x

async def process_user(user_row):
    chat_id, keywords = user_row[0], (user_row[1] or "").strip()
    if not chat_id or not keywords:
        return
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
    log.info(f"[Worker] Fetching for user {chat_id} (kw={','.join(kw_list)})")

    jobs_f = await ensure_awaitable(fetch_freelancer_jobs(kw_list))
    jobs_p = await ensure_awaitable(fetch_pph_jobs(kw_list))
    jobs_s = await ensure_awaitable(fetch_skywalker_jobs(kw_list))

    all_jobs = (jobs_f or []) + (jobs_p or []) + (jobs_s or [])

    filtered = []
    for j in all_jobs:
        if within_age(parse_iso(j.get("posted_at")), MAX_AGE_HOURS):
            filtered.append(j)

    log.info(f"[Worker] Total jobs merged: {len(filtered)}")
    for job in filtered[:MAX_SEND]:
        await send_job(BOT_TOKEN, chat_id, job)
    log.info(f"[Worker] ✅ Sent {min(len(filtered), MAX_SEND)} jobs → {chat_id}")

async def run_once():
    users = fetch_users()
    log.info(f"[Worker] Total users: {len(users)}")
    for u in users:
        try:
            await process_user(u)
        except Exception as e:
            log.error(f"[Worker] Error processing user {u}: {e}")

if __name__ == "__main__":
    log.info("[Worker] Starting background process...")
    try:
        while True:
            asyncio.run(run_once())
            log.info("[Worker] Cycle complete. Sleeping...")
            time.sleep(WORKER_INTERVAL)
    except KeyboardInterrupt:
        log.info("[Worker] Stopped manually.")
    except Exception as e:
        log.error(f"[Worker main_loop error] {e}")
