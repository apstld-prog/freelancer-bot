import os
import logging
import asyncio
from typing import List, Dict
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from db import SessionLocal, User, Keyword, JobSent, JobSaved, JobDismissed

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
AFFILIATE_PREFIX = os.getenv("AFFILIATE_PREFIX", "https://affiliate-network.com/?url=")
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is not set.")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [worker] %(levelname)s: %(message)s")
logger = logging.getLogger("freelancer-worker")
bot = Bot(BOT_TOKEN)

def affiliate_wrap(url: str) -> str:
    return f"{AFFILIATE_PREFIX}{url}"

async def fetch_jobs() -> List[Dict]:
    # TODO: replace with real fetch
    return [
        {"id": "12345","title": "Telegram Bot Developer",
         "url": "https://www.freelancer.com/projects/python/telegram-bot-job-12345",
         "description": "Looking for a Python developer to build a Telegram bot.","country": "US"},
        {"id": "67890","title": "Web Scraper Needed",
         "url": "https://www.freelancer.com/projects/python/web-scraper-job-67890",
         "description": "Need a fast scraper in Python.","country": "UK"},
    ]

def match_job_to_user(job: Dict, user: User, keywords: List[Keyword]) -> bool:
    if user.countries and user.countries != "ALL":
        allowed = {c.strip().upper() for c in (user.countries or "").split(",")}
        if job.get("country", "").upper() not in allowed:
            return False
    text = (job.get("title", "") + " " + job.get("description", "")).lower()
    return any(kw.keyword.lower() in text for kw in keywords)

async def send_job(user: User, job: Dict):
    db = SessionLocal()
    try:
        if db.query(JobSent).filter_by(user_id=user.id, job_id=job["id"]).first():
            return
        aff_url = affiliate_wrap(job["url"])
        buttons = [
            [InlineKeyboardButton("⭐ Save", callback_data=f"save:{job['id']}"),
             InlineKeyboardButton("🙈 Dismiss", callback_data=f"dismiss:{job['id']}")],
            [InlineKeyboardButton("💼 Proposal", url=aff_url),
             InlineKeyboardButton("🔗 Original", url=aff_url)],
        ]
        keyboard = InlineKeyboardMarkup(buttons)
        desc = (job.get("description") or "").strip()
        if len(desc) > 300: desc = desc[:300] + "..."
        text = f"💼 *{job['title']}*\n\n{desc}\n\n🔗 [View Job]({aff_url})"
        await bot.send_message(
            chat_id=user.telegram_id, text=text, reply_markup=keyboard,
            parse_mode="Markdown", disable_web_page_preview=True,
        )
        db.add(JobSent(user_id=user.id, job_id=job["id"])); db.commit()
    finally:
        db.close()

async def worker_loop():
    while True:
        try:
            jobs = await fetch_jobs()
            db = SessionLocal()
            try:
                users = db.query(User).all()
                for job in jobs:
                    for user in users:
                        kws = db.query(Keyword).filter_by(user_id=user.id).all()
                        if kws and match_job_to_user(job, user, kws):
                            await send_job(user, job)
            finally:
                db.close()
        except Exception as e:
            logging.exception(f"Error in worker loop: {e}")
        await asyncio.sleep(60)

def main(): asyncio.run(worker_loop())
if __name__ == "__main__": main()
