import asyncio
import logging
import os
import hashlib
from datetime import datetime, timedelta

import psycopg2
import psycopg2.extras

from platform_freelancer import fetch_freelancer_jobs
from platform_peopleperhour import fetch_pph_jobs
from platform_skywalker import fetch_skywalker_jobs
from currency_usd import usd_line

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker")

DATABASE_URL = (os.getenv("DATABASE_URL") or "").replace("postgresql+psycopg2://", "postgresql://")
FRESH_HOURS = int(os.getenv("FRESH_HOURS", "48"))
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "180"))

# ---------------- DB ----------------
def db_connect():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL env var is required")
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def ensure_sent_table():
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sent_job (
            user_id BIGINT,
            job_hash TEXT,
            sent_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC')
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sent_job_user_hash ON sent_job(user_id, job_hash)")
    conn.commit()
    cur.close()
    conn.close()

def has_been_sent(tid: int, job_hash: str) -> bool:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sent_job WHERE user_id=%s AND job_hash=%s LIMIT 1", (tid, job_hash))
    ok = cur.fetchone() is not None
    cur.close()
    conn.close()
    return ok

def mark_as_sent(tid: int, job_hash: str):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("INSERT INTO sent_job (user_id, job_hash) VALUES (%s,%s)", (tid, job_hash))
    conn.commit()
    cur.close()
    conn.close()

# ---------------- USERS ----------------
def get_users_with_keywords():
    conn = db_connect()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        'SELECT id, telegram_id, COALESCE(countries, \'ALL\') AS countries, is_active, is_blocked '
        'FROM "user" WHERE is_active=TRUE'
    )
    users = cur.fetchall() or []
    for u in users:
        db_user_id = u["id"]
        cur.execute('SELECT keyword FROM keyword WHERE user_id=%s ORDER BY id ASC', (db_user_id,))
        rows = cur.fetchall() or []
        kws = [(r["keyword"] or "").strip() for r in rows if (r.get("keyword") or "").strip()]
        u["keywords_list"] = kws
        u["keywords_str"] = ", ".join(kws)
    cur.close()
    conn.close()
    return users

# ---------------- FILTERS ----------------
def format_relative_time(ts):
    """Μετατρέπει timestamp -> '2 hours ago'."""
    try:
        dt = datetime.fromtimestamp(ts)
    except Exception:
        return ""
    delta = datetime.utcnow() - dt
    s = int(delta.total_seconds())
    if s < 60:
        return f"{s} sec ago"
    m = s // 60
    if m < 60:
        return f"{m} min ago"
    h = m // 60
    if h < 24:
        return f"{h} hours ago"
    d = h // 24
    return f"{d} days ago"

def is_fresh(job):
    ts = job.get("time_submitted") or job.get("timestamp")
    if not ts:
        return True
    try:
        job_time = datetime.fromtimestamp(ts)
    except Exception:
        return True
    return (datetime.utcnow() - job_time) <= timedelta(hours=FRESH_HOURS)

def matches_keywords(job, kw_list):
    if not kw_list:
        return False
    blob = f"{job.get('title','')} {job.get('description','')}".lower()
    for kw in kw_list:
        k = kw.lower().strip()
        if not k:
            continue
        if k in blob:
            job["matched_keyword"] = k
            return True
    return False

def matches_country(job, countries):
    if not countries or countries.upper() == "ALL":
        return True
    val = (job.get("country") or job.get("location") or "").upper()
    if not val:
        return True
    wanted = [c.strip().upper() for c in countries.split(",") if c.strip()]
    return any(c in val for c in wanted)

# ---------------- SEND ----------------
async def send_job(bot, chat_id: int, job: dict):
    try:
        title = job.get("title") or "Untitled"
        src = job.get("source") or ""
        match_kw = job.get("matched_keyword") or ""
        cur_code = job.get("budget_currency") or ""
        bmin = job.get("budget_min") or 0
        bmax = job.get("budget_max") or 0
        usd_text = usd_line(bmin, bmax, cur_code) or ""

        rel = ""
        ts = job.get("time_submitted") or job.get("timestamp")
        if ts:
            rel = format_relative_time(ts)
            job["relative_time"] = f"<b>Posted:</b> {rel}"

        text = f"<b>{title}</b>\n"
        if bmin or bmax:
            text += f"<b>Budget:</b> {bmin}–{bmax} {cur_code} {usd_text}\n"
        else:
            text += f"<b>Budget:</b> N/A\n"
        text += f"<b>Source:</b> {src}\n"
        if match_kw:
            text += f"<b>Match:</b> {match_kw}\n"
        if rel:
            text += f"<b>Posted:</b> {rel}\n"
        desc = (job.get("description") or "").strip()
        if desc:
            text += f"{desc[:400]}\n"

        kb = [
            [
                {"text": "📄 Proposal", "url": job.get("affiliate_url") or job.get("original_url")},
                {"text": "🔗 Original", "url": job.get("original_url")},
            ],
            [
                {"text": "⭐ Save", "callback_data": "job:save"},
                {"text": "🗑️ Delete", "callback_data": "job:delete"},
            ],
        ]
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup={"inline_keyboard": kb},
            disable_web_page_preview=True,
        )
        log.info("Sent job → %s: %s", chat_id, title[:60])
    except Exception as e:
        log.warning("send_job error: %s", e)

# ---------------- MAIN ----------------
async def process_user(bot, user_row):
    if user_row.get("is_blocked"):
        return
    chat_id = int(user_row["telegram_id"])
    kw_list = user_row.get("keywords_list") or []
    countries = (user_row.get("countries") or "ALL").upper()

    log.info("[Worker] Fetching for user %s (kw=%s, countries=%s)",
             chat_id, ", ".join(kw_list) if kw_list else "none", countries)

    all_jobs = []
    try:
        all_jobs.extend(await fetch_freelancer_jobs(kw_list))
        all_jobs.extend(await fetch_pph_jobs(kw_list))
        all_jobs.extend(await fetch_skywalker_jobs(kw_list))
    except Exception as e:
        log.exception("Fetch error: %s", e)

    sent = 0
    for job in all_jobs:
        if not is_fresh(job):
            continue
        if not matches_keywords(job, kw_list):
            continue
        if not matches_country(job, countries):
            continue

        jhash = hashlib.sha1((job.get("title","") + job.get("original_url","")).encode("utf-8","ignore")).hexdigest()
        if has_been_sent(chat_id, jhash):
            continue
        mark_as_sent(chat_id, jhash)
        await send_job(bot, chat_id, job)
        sent += 1
        await asyncio.sleep(1.0)

    log.info("✅ Sent %d jobs → %s", sent, chat_id)

# ---------------- LOOP ----------------
async def main_loop(bot):
    ensure_sent_table()
    while True:
        try:
            users = get_users_with_keywords()
            log.info("[Worker] Total users: %d", len(users))
            for u in users:
                await process_user(bot, u)
                await asyncio.sleep(2)
            log.info("[Worker] Cycle complete. Sleeping...")
        except Exception as e:
            log.exception("main_loop error: %s", e)
        await asyncio.sleep(WORKER_INTERVAL)

# ---------------- ENTRY ----------------
if __name__ == "__main__":
    from telegram import Bot
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN/BOT_TOKEN env var is required")
    bot = Bot(token)
    asyncio.run(main_loop(bot))
