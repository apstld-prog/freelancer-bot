import time
import os
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from db import SessionLocal, User, Keyword, JobSent

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)

UPWORK_AFFILIATE_ID = os.getenv("UPWORK_AFFILIATE_ID", "")
FREELANCER_AFFILIATE_ID = os.getenv("FREELANCER_AFFILIATE_ID", "")
FIVERR_AFFILIATE_ID = os.getenv("FIVERR_AFFILIATE_ID", "")

def build_affiliate_link(platform: str, job_url: str) -> str:
    platform = (platform or "").lower()
    if platform == "upwork" and UPWORK_AFFILIATE_ID:
        # Impact/Upwork: use your tracking deep-link if provided
        if UPWORK_AFFILIATE_ID.startswith("http"):
            return f"{UPWORK_AFFILIATE_ID}"
        return f"{job_url}?ref={UPWORK_AFFILIATE_ID}"
    elif platform == "freelancer" and FREELANCER_AFFILIATE_ID:
        return f"https://www.freelancer.com/get/{FREELANCER_AFFILIATE_ID}"
    elif platform == "fiverr" and FIVERR_AFFILIATE_ID:
        return f"https://track.fiverr.com/visit/?bta={FIVERR_AFFILIATE_ID}&brand=fiverrcpa"
    return job_url

def fetch_jobs(keyword: str, countries_csv: str):
    """
    TODO: Replace with real integrations (API/scraping).
    For now returns a mock job to validate flow & Render deployment.
    """
    countries = [c.strip().upper() for c in (countries_csv or "").split(",") if c.strip()]
    job = {
        "id": "12345",
        "title": f"{keyword} developer needed",
        "url": "https://www.upwork.com/job/12345/",
        "country": "US",
        "platform": "upwork",
    }
    if countries and job["country"].upper() not in countries:
        return []
    return [job]

def run_worker():
    while True:
        db = SessionLocal()
        users = db.query(User).all()
        for user in users:
            keywords = [k.keyword for k in db.query(Keyword).filter_by(user_id=user.id).all()]
            for kw in keywords:
                jobs = fetch_jobs(kw, user.countries)
                for job in jobs:
                    # prevent duplicate notifications
                    if db.query(JobSent).filter_by(user_id=user.id, job_id=job["id"]).first():
                        continue
                    affiliate_link = build_affiliate_link(job.get("platform",""), job["url"])
                    text = (
                        f"🚀 New Job: {job['title']}\n"
                        f"🌍 Country: {job['country']}\n"
                        f"🔗 {affiliate_link}"
                    )
                    keyboard = InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("⭐ Keep", callback_data=f"save:{job['id']}"),
                            InlineKeyboardButton("🙈 Dismiss", callback_data=f"dismiss:{job['id']}")
                        ]
                    ])
                    bot.send_message(chat_id=user.telegram_id, text=text, reply_markup=keyboard)
                    # Mark as sent so we don't resend unless user finds it via search
                    db.add(JobSent(user_id=user.id, job_id=job["id"]))
                    db.commit()
        db.close()
        time.sleep(120)  # poll every 2 minutes

if __name__ == "__main__":
    run_worker()
