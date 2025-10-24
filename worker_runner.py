import asyncio
import logging
import time
import hashlib
import os
from datetime import datetime, timedelta
import psycopg2
import psycopg2.extras

from platform_freelancer import fetch_freelancer_jobs
from platform_peopleperhour import fetch_pph_jobs
from platform_skywalker import fetch_skywalker_jobs
from currency_usd import usd_line  # ✅ διορθωμένο import

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker")

DATABASE_URL = os.getenv("DATABASE_URL")
FRESH_HOURS = int(os.getenv("FRESH_HOURS", "48"))

def db_connect():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def get_all_users():
    conn = db_connect()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('SELECT telegram_id, keywords, countries, is_admin, is_blocked, is_active FROM "user" WHERE is_active = true')
    users = cur.fetchall()
    cur.close()
    conn.close()
    return users

def get_sent_hashes():
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS sent_job (user_id BIGINT, job_hash TEXT, sent_at TIMESTAMP)")
    conn.commit()
    cur.close()
    conn.close()

def has_been_sent(user_id, job_hash):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sent_job WHERE user_id=%s AND job_hash=%s LIMIT 1", (user_id, job_hash))
    exists = cur.fetchone()
    cur.close()
    conn.close()
    return bool(exists)

def mark_as_sent(user_id, job_hash):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("INSERT INTO sent_job (user_id, job_hash, sent_at) VALUES (%s,%s,NOW())", (user_id, job_hash))
    conn.commit()
    cur.close()
    conn.close()

def is_fresh(job):
    if not job.get("time_submitted"):
        return True
    job_time = datetime.fromtimestamp(job["time_submitted"])
    return (datetime.utcnow() - job_time) < timedelta(hours=FRESH_HOURS)

def matches_keywords(job, keywords):
    if not keywords:
        return False
    kw_list = [k.strip().lower() for k in keywords.split(",") if k.strip()]
    text = (job.get("title", "") + " " + job.get("description", "")).lower()
    for kw in kw_list:
        if kw in text:
            job["matched_keyword"] = kw
            return True
    return False

def matches_country(job, countries):
    if not countries or countries == "ALL":
        return True
    if not job.get("country") and not job.get("location"):
        return False
    loc = (job.get("country") or job.get("location") or "").upper()
    for c in [x.strip().upper() for x in countries.split(",")]:
        if c in loc:
            return True
    return False

async def send_job(bot, user_id, job):
    try:
        title = job.get("title", "Untitled")
        src = job.get("source", "")
        match_kw = job.get("matched_keyword", "")
        budget_cur = job.get("budget_currency", "")
        budget_min = job.get("budget_min") or 0
        budget_max = job.get("budget_max") or 0
        usd_text = usd_line(budget_min, budget_max, budget_cur) or ""  # ✅ σωστό όνομα συνάρτησης

        text = f"*{title}*\n"
        if budget_min or budget_max:
            text += f"Budget: {budget_min}–{budget_max} {budget_cur} {usd_text}\n"
        else:
            text += f"Budget: N/A\n"
        text += f"Source: {src}\n"
        if match_kw:
            text += f"Match: {match_kw}\n"
        desc = job.get("description", "")
        if desc:
            text += f"📝 {desc[:200]}\n"
        text += f"{job.get('relative_time','')}\n"

        buttons = [
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
            chat_id=user_id,
            text=text,
            parse_mode="Markdown",
            reply_markup={"inline_keyboard": buttons},
        )
        log.info(f"Sent job → {user_id}: {title[:40]}")

    except Exception as e:
        log.warning(f"Send failed {e}")

async def process_user(bot, user):
    if user["is_blocked"]:
        return
    user_id = user["telegram_id"]
    keywords = user.get("keywords") or ""
    countries = (user.get("countries") or "ALL").upper()

    log.info(f"[Worker] Fetching for user {user_id} (keywords={keywords}, countries={countries})")
    all_jobs = []
    try:
        all_jobs += fetch_freelancer_jobs(keywords.split(","))
        all_jobs += fetch_pph_jobs(keywords.split(","))
        all_jobs += fetch_skywalker_jobs(keywords.split(","))
    except Exception as e:
        log.error(f"Job fetch error: {e}")

    sent = 0
    for job in all_jobs:
        if not is_fresh(job):
            continue
        if not matches_keywords(job, keywords):
            continue
        if not matches_country(job, countries):
            continue

        job_hash = hashlib.sha1((job.get("title","")+job.get("original_url","")).encode()).hexdigest()
        if has_been_sent(user_id, job_hash):
            continue
        mark_as_sent(user_id, job_hash)

        await send_job(bot, user_id, job)
        sent += 1
        await asyncio.sleep(1.5)

    log.info(f"✅ Sent {sent} jobs → {user_id}")

async def main_loop(bot):
    get_sent_hashes()
    while True:
        users = get_all_users()
        log.info(f"[Worker] Total users: {len(users)}")
        for u in users:
            await process_user(bot, u)
            await asyncio.sleep(3)
        log.info(f"[Worker] Cycle complete. Sleeping...")
        await asyncio.sleep(int(os.getenv("WORKER_INTERVAL", "180")))

if __name__ == "__main__":
    from telegram import Bot
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    bot = Bot(BOT_TOKEN)
    asyncio.run(main_loop(bot))
