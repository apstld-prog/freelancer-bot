import time, logging
from db import get_session
from sqlalchemy import text
from platform_freelancer import fetch_freelancer_jobs
from platform_peopleperhour import fetch_peopleperhour_jobs
from platform_skywalker import fetch_skywalker_jobs
from job_logic import make_key, match_keywords
from telegram import Bot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")

bot = Bot(token="8301080604:AAF7Hsb_ImfJHiJVYTTXzQOwgI37h8XlEKc")

def ensure_sent_table():
    with get_session() as s:
        s.execute(text("""
        CREATE TABLE IF NOT EXISTS sent_job (
            id SERIAL PRIMARY KEY,
            job_key TEXT UNIQUE,
            sent_at TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'UTC')
        );
        """))
        s.commit()

def get_keywords():
    with get_session() as s:
        rows = s.execute(text("SELECT DISTINCT value FROM keyword")).fetchall()
    return [r[0] for r in rows]

def already_sent(key):
    with get_session() as s:
        return s.execute(text("SELECT 1 FROM sent_job WHERE job_key=:k"), {"k": key}).fetchone() is not None

def mark_sent(key):
    with get_session() as s:
        s.execute(text("INSERT INTO sent_job (job_key) VALUES (:k) ON CONFLICT DO NOTHING"), {"k": key})
        s.commit()

def send_to_users(job):
    msg = f"💼 <b>{job['title']}</b>\n\n{job['description']}\n\n🔗 {job['url']}"
    with get_session() as s:
        users = s.execute(text("SELECT telegram_id FROM \"user\"")).fetchall()
    for u in users:
        try:
            bot.send_message(chat_id=u[0], text=msg, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"send fail: {e}")

def main_loop():
    ensure_sent_table()
    logger.info("[Worker] ✅ Running (interval=60s)")
    while True:
        keywords = get_keywords()
        jobs = []
        for fn in [fetch_freelancer_jobs, fetch_peopleperhour_jobs, fetch_skywalker_jobs]:
            try:
                jobs.extend(fn(keywords))
            except Exception as e:
                logger.error(f"[{fn.__name__}] fetch error: {e}")
        for job in jobs:
            key = make_key(job)
            if already_sent(key): continue
            if not match_keywords(job, keywords): continue
            send_to_users(job)
            mark_sent(key)
        logger.info(f"[Worker] cycle completed — keywords={len(keywords)}, items={len(jobs)}")
        time.sleep(60)

if __name__ == "__main__":
    main_loop()
