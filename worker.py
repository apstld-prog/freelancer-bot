import os
import time
import logging
import random
from datetime import datetime
from urllib.parse import quote_plus

from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from db import SessionLocal, User, Keyword, JobSent

# ------------------------------------------------------------------------------
# Environment
# ------------------------------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "120"))  # seconds
DEBUG = os.getenv("DEBUG", "0") == "1"
MOCK_JOBS = os.getenv("MOCK_JOBS", "1") == "1"  # generate sample jobs for testing

FREELANCER_AFFILIATE_ID = os.getenv("FREELANCER_AFFILIATE_ID", "")  # e.g. your Freelancer username
FIVERR_AFFILIATE_ID = os.getenv("FIVERR_AFFILIATE_ID", "")          # e.g. bta id (1146042)

# ------------------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------------------
log_level = logging.DEBUG if DEBUG else logging.INFO
logging.basicConfig(
    level=log_level,
    format="%(asctime)s [worker] %(levelname)s: %(message)s",
)
logger = logging.getLogger("freelancer-worker")

if not BOT_TOKEN:
    logger.warning("BOT_TOKEN is empty! Worker will not be able to send Telegram messages.")

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None

# ------------------------------------------------------------------------------
# Affiliate links
# ------------------------------------------------------------------------------
def build_affiliate_link(platform: str, job_url: str) -> str:
    p = (platform or "").lower()
    if p == "freelancer" and FREELANCER_AFFILIATE_ID:
        # Freelancer referral / deep link. If you have a specific job URL, you could still send base referral.
        return f"https://www.freelancer.com/get/{FREELANCER_AFFILIATE_ID}"
    if p == "fiverr" and FIVERR_AFFILIATE_ID:
        enc = quote_plus(job_url)
        # CPA brand can be 'fiverrcpa' or 'fiverrmarketplace' depending on your program
        return f"https://track.fiverr.com/visit/?bta={FIVERR_AFFILIATE_ID}&brand=fiverrcpa&url={enc}"
    return job_url

# ------------------------------------------------------------------------------
# Job fetching (mock for now with DEBUG logs)
# Replace this with real API/RSS integrations when available.
# ------------------------------------------------------------------------------
COUNTRY_POOL = ["US", "UK", "DE", "GR", "FR", "CA", "AU", "NL", "IT", "ES"]

def mock_jobs(keyword: str, n: int = 3):
    """Generate deterministic-looking mock jobs for testing."""
    out = []
    now = int(time.time())
    for i in range(n):
        platform = random.choice(["freelancer", "fiverr"])
        country = random.choice(COUNTRY_POOL)
        job_id = f"{platform[:3]}-{keyword[:3].upper()}-{now}-{i}"
        title = f"[{platform.title()}] {keyword} project #{i+1}"
        url = (
            "https://www.freelancer.com/projects/python/telegram-bot-automation"
            if platform == "freelancer"
            else "https://www.fiverr.com/categories/programming-tech"
        )
        out.append(
            {
                "id": job_id,
                "title": title,
                "url": url,
                "country": country,
                "platform": platform,
            }
        )
    return out

def fetch_jobs(keyword: str, countries_csv: str):
    """
    Fetch jobs for a given keyword and optional country filter.
    Currently returns mock data when MOCK_JOBS=1.
    Replace with real integrations (Upwork/Freelancer/Fiverr) later.
    """
    if MOCK_JOBS:
        jobs = mock_jobs(keyword, n=3)
        logger.debug(f"[fetch] keyword='{keyword}' generated {len(jobs)} mock jobs")
    else:
        # TODO: integrate real sources; keep logs rich for debugging
        jobs = []
        logger.debug(f"[fetch] keyword='{keyword}' real fetch not implemented -> 0 jobs")

    # Country filter
    countries = [c.strip().upper() for c in (countries_csv or "").split(",") if c.strip()]
    if countries:
        before = len(jobs)
        jobs = [j for j in jobs if j["country"].upper() in countries]
        logger.debug(f"[filter] countries={countries} kept {len(jobs)}/{before} jobs")

    return jobs

# ------------------------------------------------------------------------------
# Main worker loop
# ------------------------------------------------------------------------------
def process_user(db, user: User):
    uid = user.telegram_id
    kw_rows = db.query(Keyword).filter_by(user_id=user.id).all()
    keywords = [k.keyword for k in kw_rows]
    logger.info(f"Scanning user={uid} keywords={keywords or ['<none>']} countries={user.countries or 'ALL'}")

    if not keywords:
        logger.debug(f"user={uid} has no keywords; skipping.")
        return

    # iterate keywords
    for kw in keywords:
        try:
            jobs = fetch_jobs(kw, user.countries)
        except Exception as e:
            logger.exception(f"fetch_jobs failed for user={uid}, keyword='{kw}': {e}")
            continue

        logger.info(f"user={uid} keyword='{kw}' -> found {len(jobs)} jobs")

        for job in jobs:
            job_id = job.get("id")
            platform = job.get("platform", "")
            # duplicate check
            exists = db.query(JobSent).filter_by(user_id=user.id, job_id=job_id).first()
            if exists:
                logger.debug(f"user={uid} job_id={job_id} already sent. skipping.")
                continue

            affiliate_link = build_affiliate_link(platform, job["url"])
            text = (
                f"🚀 New Opportunity: {job['title']}\n"
                f"🌍 Country: {job['country']}\n"
                f"🧭 Platform: {platform.title() if platform else 'N/A'}\n"
                f"🔗 Link: {affiliate_link}"
            )

            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⭐ Keep", callback_data=f"save:{job_id}"),
                    InlineKeyboardButton("🙈 Dismiss", callback_data=f"dismiss:{job_id}"),
                ],
                [
                    InlineKeyboardButton(
                        "✍️ Proposal",
                        callback_data=f"proposal:{job_id}|{platform}|{affiliate_link}|{quote_plus(job['title'])}"
                    ),
                    InlineKeyboardButton("🌐 Open", url=affiliate_link),
                ]
            ])

            if bot:
                try:
                    bot.send_message(chat_id=uid, text=text, reply_markup=kb)
                    logger.info(f"sent job_id={job_id} to user={uid} (platform={platform}, country={job['country']})")
                except Exception as te:
                    logger.exception(f"Telegram send failed for user={uid}, job_id={job_id}: {te}")
                    continue
            else:
                logger.warning("BOT_TOKEN not set; skipping Telegram send.")

            # mark as sent
            try:
                db.add(JobSent(user_id=user.id, job_id=job_id))
                db.commit()
                logger.debug(f"marked job_id={job_id} as sent for user={uid}")
            except Exception as se:
                db.rollback()
                logger.exception(f"DB commit failed for user={uid}, job_id={job_id}: {se}")

def run_worker():
    logger.info("Worker starting...")
    logger.info(f"DEBUG={DEBUG} MOCK_JOBS={MOCK_JOBS} INTERVAL={WORKER_INTERVAL}s")
    heartbeat_next = time.time() + 300  # every 5 minutes

    while True:
        loop_start = time.time()
        try:
            db = SessionLocal()
            users = db.query(User).all()
            logger.info(f"Loaded {len(users)} users from DB")

            for user in users:
                try:
                    process_user(db, user)
                except Exception as ue:
                    logger.exception(f"Unhandled error processing user={user.telegram_id}: {ue}")

        except Exception as e:
            logger.exception(f"Top-level loop error: {e}")
        finally:
            try:
                db.close()
            except Exception:
                pass

        # heartbeat
        now = time.time()
        if now >= heartbeat_next:
            logger.info(f"Heartbeat: {datetime.utcnow().isoformat()}Z")
            heartbeat_next = now + 300

        elapsed = time.time() - loop_start
        sleep_for = max(1, WORKER_INTERVAL - int(elapsed))
        logger.debug(f"Loop took {elapsed:.2f}s, sleeping {sleep_for}s")
        time.sleep(sleep_for)

# ------------------------------------------------------------------------------
# Entrypoint
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        run_worker()
    except KeyboardInterrupt:
        logger.info("Worker stopped by KeyboardInterrupt")
