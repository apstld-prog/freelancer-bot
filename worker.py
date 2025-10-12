import os
import time
import logging
from datetime import datetime
from sqlalchemy import text
from db import get_session
from job_logic import make_key, match_keywords
from platform_freelancer import fetch_freelancer_jobs
from platform_peopleperhour import fetch_peopleperhour_jobs
from platform_kariera import fetch_kariera_jobs
from platform_careerjet import fetch_careerjet_jobs
from platform_skywalker import fetch_skywalker_jobs
from db_events import log_platform_event
from telegram import Bot

logging.basicConfig(level=logging.INFO, format="%(levelname)s:worker:%(message)s")
logger = logging.getLogger("worker")

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "60"))

def cleanup_old_jobs():
    with get_session() as s:
        s.execute(text("DELETE FROM sent_job WHERE sent_at < (NOW() AT TIME ZONE 'UTC') - INTERVAL '7 days'"))
        s.commit()

def ensure_sent_table():
    with get_session() as s:
        s.execute(text("""
            CREATE TABLE IF NOT EXISTS sent_job (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                job_key TEXT NOT NULL,
                sent_at TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'UTC')
            )
        """))
        s.commit()

def get_all_users():
    with get_session() as s:
        return s.execute(text("SELECT id, telegram_id FROM \"user\" WHERE is_active = TRUE")).fetchall()

def get_keywords():
    with get_session() as s:
        return [r[0] for r in s.execute(text("SELECT DISTINCT value FROM keyword")).fetchall()]

def send_job_to_user(user_tg, job):
    try:
        text_msg = (
            f"🧩 <b>{job['title']}</b>\n\n"
            f"💰 <b>Budget:</b> {job.get('budget', 'N/A')}\n"
            f"🌐 <b>Source:</b> {job.get('platform', 'Unknown')}\n"
            f"📅 <b>Date:</b> {job.get('created_at', 'N/A')}\n\n"
            f"{job.get('description', '')[:500]}...\n\n"
            f"<a href='{job.get('affiliate_url', job.get('original_url', '#'))}'>🔗 Open Project</a>"
        )
        bot.send_message(chat_id=user_tg, text=text_msg, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"[deliver] send error: {e}")

def main_worker():
    logger.info(f"[Worker] ✅ Running (interval={WORKER_INTERVAL}s)")
    ensure_sent_table()

    while True:
        try:
            cleanup_old_jobs()
            keywords = get_keywords()
            if not keywords:
                time.sleep(WORKER_INTERVAL)
                continue

            all_jobs = []
            platforms = [
                ("freelancer", fetch_freelancer_jobs),
                ("peopleperhour", fetch_peopleperhour_jobs),
                ("kariera", fetch_kariera_jobs),
                ("careerjet", fetch_careerjet_jobs),
                ("skywalker", fetch_skywalker_jobs)
            ]

            for name, func in platforms:
                try:
                    jobs = func(keywords)
                    all_jobs.extend(jobs)
                    log_platform_event(name, len(jobs))
                except Exception as e:
                    logger.error(f"[{name}] fetch error: {e}")

            logger.info(f"[Worker] cycle completed — keywords={len(keywords)}, items={len(all_jobs)}")
            users = get_all_users()
            logger.info(f"[deliver] users loaded: {len(users)}")

            with get_session() as s:
                for job in all_jobs:
                    key = make_key(job)
                    for user in users:
                        exists = s.execute(
                            text("SELECT 1 FROM sent_job WHERE user_id=:u AND job_key=:k"),
                            {"u": user.id, "k": key}
                        ).fetchone()
                        if exists:
                            continue
                        send_job_to_user(user.telegram_id, job)
                        s.execute(
                            text("INSERT INTO sent_job (user_id, job_key) VALUES (:u, :k)"),
                            {"u": user.id, "k": key}
                        )
                s.commit()

        except Exception as e:
            logger.error(f"[Worker] error: {e}")
        time.sleep(WORKER_INTERVAL)

if __name__ == "__main__":
    logger.info("[Worker] Launching...")
    main_worker()
