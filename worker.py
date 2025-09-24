import time
import os
from urllib.parse import quote_plus
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from db import SessionLocal, User, Keyword, JobSent

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)

# Affiliate IDs
FREELANCER_AFFILIATE_ID = os.getenv("FREELANCER_AFFILIATE_ID", "")  # e.g. your Freelancer username
FIVERR_AFFILIATE_ID = os.getenv("FIVERR_AFFILIATE_ID", "")          # e.g. 1146042 (bta)

def build_affiliate_link(platform: str, job_url: str) -> str:
    """Return an affiliate-wrapped URL for supported platforms."""
    p = (platform or "").lower()
    if p == "freelancer" and FREELANCER_AFFILIATE_ID:
        # Freelancer referral link sends user to sign up / site
        return f"https://www.freelancer.com/get/{FREELANCER_AFFILIATE_ID}"
    if p == "fiverr" and FIVERR_AFFILIATE_ID:
        # Build a deep link to Fiverr with your affiliate ID (bta)
        enc = quote_plus(job_url)
        return f"https://track.fiverr.com/visit/?bta={FIVERR_AFFILIATE_ID}&brand=fiverrcpa&url={enc}"
    # Default: return original
    return job_url

def fetch_jobs(keyword: str, countries_csv: str):
    """
    TODO: Replace with real integrations (API/scraping/RSS).
    For now, returns mock jobs to verify flow. Includes both platforms.
    """
    countries = [c.strip().upper() for c in (countries_csv or "").split(",") if c.strip()]
    sample = [
        {
            "id": "frl-001",
            "title": f"[Freelancer] {keyword} automation needed",
            "url": "https://www.freelancer.com/projects/python/telegram-bot-automation",
            "country": "US",
            "platform": "freelancer",
        },
        {
            "id": "fvr-002",
            "title": f"[Fiverr] {keyword} gig setup / consulting",
            "url": "https://www.fiverr.com/categories/programming-tech",
            "country": "UK",
            "platform": "fiverr",
        },
    ]
    if countries:
        sample = [j for j in sample if j["country"].upper() in countries]
    return sample

def run_worker():
    while True:
        db = SessionLocal()
        users = db.query(User).all()
        for user in users:
            keywords = [k.keyword for k in db.query(Keyword).filter_by(user_id=user.id).all()]
            for kw in keywords:
                jobs = fetch_jobs(kw, user.countries)
                for job in jobs:
                    # Avoid duplicates
                    if db.query(JobSent).filter_by(user_id=user.id, job_id=job["id"]).first():
                        continue

                    affiliate_link = build_affiliate_link(job.get("platform", ""), job["url"])
                    text = (
                        f"🚀 New Opportunity: {job['title']}\n"
                        f"🌍 Country: {job['country']}\n"
                        f"🧭 Platform: {job.get('platform','').title()}\n"
                        f"🔗 Link: {affiliate_link}"
                    )

                    # Inline buttons: Keep, Dismiss, Proposal, Open
                    kb = InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("⭐ Keep", callback_data=f"save:{job['id']}"),
                            InlineKeyboardButton("🙈 Dismiss", callback_data=f"dismiss:{job['id']}"),
                        ],
                        [
                            InlineKeyboardButton("✍️ Proposal", callback_data=f"proposal:{job['id']}|{job.get('platform','')}|{affiliate_link}|{quote_plus(job['title'])}"),
                            InlineKeyboardButton("🌐 Open", url=affiliate_link),
                        ]
                    ])

                    bot.send_message(chat_id=user.telegram_id, text=text, reply_markup=kb)
                    # Mark as sent so we don't send again
                    db.add(JobSent(user_id=user.id, job_id=job["id"]))
                    db.commit()
        db.close()
        time.sleep(120)  # every 2 minutes

if __name__ == "__main__":
    run_worker()
