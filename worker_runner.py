import asyncio
import httpx
import logging
import os
import psycopg2
import hashlib
from datetime import datetime, timezone, timedelta
from platform_freelancer import fetch_freelancer_jobs
from platform_peopleperhour import fetch_pph_jobs
from platform_skywalker import fetch_skywalker_jobs

log = logging.getLogger("worker")

DB_URL = os.getenv("DATABASE_URL")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "180"))
KEYWORD_FILTER_MODE = os.getenv("KEYWORD_FILTER_MODE", "on")

# --- Database utilities ---
def db_connect():
    return psycopg2.connect(DB_URL)

def ensure_sent_table():
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sent_job (
                id SERIAL PRIMARY KEY,
                sent_at TIMESTAMPTZ DEFAULT NOW(),
                job_hash TEXT NOT NULL,
                user_id BIGINT NOT NULL
            );
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_sent_job_user_hash
            ON sent_job(user_id, job_hash);
        """)
        conn.commit()

def get_all_users():
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT id, keywords, countries FROM "user"')
        rows = cur.fetchall()
        return [{"id": r[0], "keywords": r[1] or "", "countries": r[2] or "ALL"} for r in rows]

def has_been_sent(user_id, job_hash):
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM sent_job WHERE user_id=%s AND job_hash=%s", (user_id, job_hash))
        return cur.fetchone() is not None

def mark_as_sent(user_id, job_hash):
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO sent_job (user_id, job_hash) VALUES (%s,%s)", (user_id, job_hash))
        conn.commit()

# --- Telegram send utility ---
async def send_job(tid, job, client):
    try:
        title = job.get("title", "No title")
        desc = job.get("description", "")
        url = job.get("affiliate_url") or job.get("original_url") or ""
        source = job.get("source", "").capitalize()
        budget = job.get("budget_currency", "")
        posted_at = job.get("timestamp")

        if posted_at:
            age = datetime.now(tz=timezone.utc) - datetime.fromtimestamp(posted_at, tz=timezone.utc)
            if age.days > 0:
                posted_str = f"{age.days} day(s) ago"
            elif age.seconds > 3600:
                posted_str = f"{age.seconds // 3600} hour(s) ago"
            elif age.seconds > 60:
                posted_str = f"{age.seconds // 60} min(s) ago"
            else:
                posted_str = "just now"
        else:
            posted_str = ""

        msg = (
            f"📢 <b>{title}</b>\n"
            f"💼 <b>Source:</b> {source}\n"
            f"💰 <b>Budget:</b> {budget}\n"
            f"🕒 <b>Posted:</b> {posted_str}\n\n"
            f"{desc.strip()}\n\n"
        )

        kb = {"inline_keyboard": [[{"text": "🌐 View Job", "url": str(url)}]]} if url else None

        r = await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": tid, "text": msg, "parse_mode": "HTML", "reply_markup": kb},
        )
        if r.status_code != 200:
            log.warning(f"send_job error {r.status_code}: {r.text}")

    except Exception as e:
        log.warning(f"send_job error: {e}")

# --- Hash generator ---
def job_hash(job):
    base = (
        (job.get("title", "") + (job.get("original_url", "") or "") + (job.get("source", "") or ""))
        .encode("utf-8", "ignore")
    )
    return hashlib.sha1(base).hexdigest()

# --- Worker core ---
async def process_user(client, user):
    tid = user["id"]
    kw_list = [k.strip() for k in (user["keywords"] or "").split(",") if k.strip()]
    log.info(f"[Worker] Fetching for user {tid} (kw={', '.join(kw_list) or 'none'}, countries={user['countries']})")

    all_jobs = []

    try:
        jobs_f = await fetch_freelancer_jobs(kw_list)
        all_jobs.extend(jobs_f)
        log.info(f"[Freelancer] merged {len(jobs_f)}")
    except Exception as e:
        log.warning(f"[Worker] Freelancer error: {e}")

    try:
        jobs_p = await fetch_pph_jobs(kw_list)
        all_jobs.extend(jobs_p)
        log.info(f"[PeoplePerHour] merged {len(jobs_p)}")
    except Exception as e:
        log.warning(f"[Worker] PPH error: {e}")

    try:
        jobs_s = await fetch_skywalker_jobs(kw_list)
        all_jobs.extend(jobs_s)
        log.info(f"[Skywalker] merged {len(jobs_s)}")
    except Exception as e:
        log.warning(f"[Worker] Skywalker error: {e}")

    # --- Filter jobs (max 48 hours old) ---
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=48)
    filtered_jobs = []
    for j in all_jobs:
        ts = j.get("timestamp")
        if ts:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            if dt >= cutoff:
                filtered_jobs.append(j)
        else:
            filtered_jobs.append(j)

    # --- Send ---
    sent_count = 0
    for job in filtered_jobs:
        try:
            h = job_hash(job)
            if has_been_sent(tid, h):
                continue
            await send_job(tid, job, client)
            mark_as_sent(tid, h)
            sent_count += 1
        except Exception as e:
            log.warning(f"[Worker] send failed: {e}")

    log.info(f"[Worker] ✅ Sent {sent_count} jobs → {tid}")

# --- Main loop ---
async def main_loop():
    ensure_sent_table()
    log.info("[DB] Table check complete.")

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            try:
                users = get_all_users()
                log.info(f"[Worker] Total users: {len(users)}")
                for u in users:
                    await process_user(client, u)
            except Exception as e:
                log.error(f"[Worker main_loop error] {e}")
            log.info("[Worker] Cycle complete. Sleeping...")
            await asyncio.sleep(WORKER_INTERVAL)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main_loop())
