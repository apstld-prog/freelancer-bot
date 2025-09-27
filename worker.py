import os
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any

import httpx
from sqlalchemy.orm import joinedload
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, constants

from db import SessionLocal, User, Keyword, JobSent

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [worker] %(levelname)s: %(message)s")
logger = logging.getLogger("worker")

# ---------------- Config ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is not set.")

FREELANCER_REF_CODE = os.getenv("FREELANCER_REF_CODE", "").strip()
FIVERR_AFF_TEMPLATE = os.getenv("FIVERR_AFF_TEMPLATE", "").strip()
AFFILIATE_PREFIX = os.getenv("AFFILIATE_PREFIX", "").strip()

SEARCH_MODE = os.getenv("SEARCH_MODE", "all").lower()  # "all" or "single"
INTERVAL = int(os.getenv("WORKER_INTERVAL", "300"))

# Reusable Telegram bot
bot = Bot(BOT_TOKEN)

# ---------------- Helpers ----------------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def user_is_active(u: User) -> bool:
    if getattr(u, "is_blocked", False):
        return False
    t = now_utc()
    if getattr(u, "access_until", None) and u.access_until >= t:
        return True
    if getattr(u, "trial_until", None) and u.trial_until >= t:
        return True
    return False

def affiliate_wrap(url: str) -> str:
    return f"{AFFILIATE_PREFIX}{url}" if AFFILIATE_PREFIX else url

def aff_for_source(source: str, url: str) -> str:
    # Fiverr deep link supports {kw} pattern; here url may already be the final link.
    if source == "fiverr" and FIVERR_AFF_TEMPLATE:
        return url
    # Freelancer: append ?f=<code> if provided
    if source == "freelancer" and FREELANCER_REF_CODE and "freelancer.com" in url:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}f={FREELANCER_REF_CODE}"
    # Fallback global prefix
    return affiliate_wrap(url)

# ---------------- Fetchers ----------------
async def fetch_freelancer(keywords: List[str]) -> List[Dict[str, Any]]:
    """Fetch active projects from Freelancer public API using referral code."""
    if not FREELANCER_REF_CODE:
        logger.warning("Freelancer ref code missing, skipping Freelancer API.")
        return []

    base_url = "https://www.freelancer.com/api/projects/0.1/projects/active/"
    queries: List[str] = []

    if not keywords:
        return []

    if SEARCH_MODE == "single":
        queries.extend(keywords)
    else:
        # default: all keywords in one query, comma-separated
        queries.append(",".join(keywords))

    out: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=25) as client:
        for q in queries:
            params = {
                "query": q,
                "limit": 20,
                "compact": "true",
                "user_details": "true",
                "job_details": "true",
                "full_description": "true",
                "referrer": FREELANCER_REF_CODE,
            }
            try:
                r = await client.get(base_url, params=params)
                if r.status_code != 200:
                    logger.warning("Freelancer API non-200 (%s) for query '%s'", r.status_code, q)
                    continue
                data = r.json()
                for pr in data.get("result", {}).get("projects", []):
                    pid = pr.get("id")
                    title = pr.get("title") or "Untitled"
                    desc = pr.get("preview_description") or pr.get("description") or ""
                    url = f"https://www.freelancer.com/projects/{pid}"
                    out.append({
                        "id": f"freelancer-{pid}",
                        "title": title,
                        "description": desc,
                        "url": url,
                        "source": "freelancer",
                    })
            except Exception as e:
                logger.warning("Error fetching Freelancer API for '%s': %s", q, e)
    return out

async def fetch_fiverr(keywords: List[str]) -> List[Dict[str, Any]]:
    """Construct Fiverr affiliate links (no official job feed)."""
    if not FIVERR_AFF_TEMPLATE:
        logger.warning("Fiverr affiliate template missing (FIVERR_AFF_TEMPLATE), skipping.")
        return []

    out: List[Dict[str, Any]] = []
    for kw in keywords:
        url = FIVERR_AFF_TEMPLATE.replace("{kw}", kw)
        out.append({
            "id": f"fiverr-{kw}-{int(now_utc().timestamp())}",
            "title": f"Fiverr services for {kw}",
            "description": f"Browse Fiverr gigs related to '{kw}'.",
            "url": url,
            "source": "fiverr",
        })
    return out

# ---------------- Sending ----------------
async def send_job_to_user(u: User, job: Dict[str, Any]) -> None:
    text_desc = (job.get("description") or "").strip()
    if len(text_desc) > 600:
        text_desc = text_desc[:600] + "…"

    final_url = aff_for_source(job.get("source", ""), job.get("url", ""))
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Open", url=final_url)]])

    text = f"💼 *{job.get('title', 'New opportunity')}*\n\n{text_desc}"
    try:
        await bot.send_message(
            chat_id=u.telegram_id,
            text=text,
            parse_mode=constants.ParseMode.MARKDOWN,
            reply_markup=kb,
            disable_web_page_preview=True,
        )
        logger.info("Sent job %s to %s", job.get("id"), u.telegram_id)
    except Exception as e:
        logger.warning("Error sending job %s to %s: %s", job.get("id"), u.telegram_id, e)

# ---------------- Main loop ----------------
async def worker_cycle():
    db = SessionLocal()
    try:
        users = db.query(User).options(joinedload(User.keywords)).all()
        for u in users:
            if not user_is_active(u):
                continue

            kws = [k.keyword for k in u.keywords]
            if not kws:
                continue

            jobs: List[Dict[str, Any]] = []
            # Only Freelancer + Fiverr for now
            jobs.extend(await fetch_freelancer(kws))
            jobs.extend(await fetch_fiverr(kws))

            # Get already sent IDs for this user
            sent_ids = {row.job_id for row in db.query(JobSent).filter_by(user_id=u.id).all()}

            for job in jobs:
                jid = job.get("id")
                if not jid or jid in sent_ids:
                    continue

                # Save sent marker (NOTE: JobSent has only user_id & job_id in your model)
                db.add(JobSent(user_id=u.id, job_id=jid))
                db.commit()

                await send_job_to_user(u, job)

        logger.info("Worker cycle complete.")
    except Exception as e:
        logger.exception("Worker cycle error: %s", e)
    finally:
        db.close()

async def worker_loop():
    logger.info("Worker loop running every %ss (SEARCH_MODE=%s)", INTERVAL, SEARCH_MODE)
    while True:
        await worker_cycle()
        await asyncio.sleep(INTERVAL)

if __name__ == "__main__":
    asyncio.run(worker_loop())
