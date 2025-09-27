import os
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any

import httpx
import feedparser
from sqlalchemy.orm import joinedload

from db import SessionLocal, User, Keyword, JobSent
from bot import affiliate_wrap, user_is_active, now_utc

logging.basicConfig(level=logging.INFO, format="%(asctime)s [worker] %(levelname)s: %(message)s")
logger = logging.getLogger("worker")

# Config
INTERVAL = int(os.getenv("WORKER_INTERVAL", "300"))
SEARCH_MODE = os.getenv("SEARCH_MODE", "all")  # "all" or "single"
FREELANCER_REF_CODE = os.getenv("FREELANCER_REF_CODE", "")
FIVERR_AFF_TEMPLATE = os.getenv("FIVERR_AFF_TEMPLATE", "")


# ------------------- Fetchers -------------------

async def fetch_freelancer(keywords: List[str]) -> List[Dict[str, Any]]:
    """Fetch projects from Freelancer API using referral code"""
    if not FREELANCER_REF_CODE:
        logger.warning("Freelancer ref code missing, skipping.")
        return []

    results = []
    base_url = "https://www.freelancer.com/api/projects/0.1/projects/active/"

    queries = []
    if SEARCH_MODE == "all":
        queries.append(",".join(keywords))
    else:
        queries.extend(keywords)

    async with httpx.AsyncClient(timeout=20) as client:
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
                    logger.warning(f"Freelancer API non-200: {r.status_code}")
                    continue
                data = r.json()
                for pr in data.get("result", {}).get("projects", []):
                    results.append({
                        "id": f"freelancer-{pr['id']}",
                        "title": pr.get("title", "Untitled"),
                        "description": pr.get("preview_description", ""),
                        "url": f"https://www.freelancer.com/projects/{pr['id']}?f={FREELANCER_REF_CODE}",
                        "source": "freelancer",
                    })
            except Exception as e:
                logger.warning(f"Error fetching Freelancer API: {e}")
    return results


async def fetch_fiverr(keywords: List[str]) -> List[Dict[str, Any]]:
    """Generate Fiverr affiliate links (no official jobs API)"""
    if not FIVERR_AFF_TEMPLATE:
        logger.warning("Fiverr affiliate template missing, skipping.")
        return []

    results = []
    for kw in keywords:
        url = FIVERR_AFF_TEMPLATE.replace("{kw}", kw)
        results.append({
            "id": f"fiverr-{kw}-{int(datetime.now().timestamp())}",
            "title": f"Fiverr services for {kw}",
            "description": f"Browse Fiverr gigs related to {kw}.",
            "url": url,
            "source": "fiverr",
        })
    return results


async def fetch_placeholder(name: str) -> List[Dict[str, Any]]:
    logger.warning(f"{name} fetcher not implemented yet.")
    return []


# ------------------- Core Worker -------------------

async def worker_loop():
    logger.info(f"Worker loop running every {INTERVAL}s, mode={SEARCH_MODE}")
    while True:
        try:
            db = SessionLocal()
            users = db.query(User).options(joinedload(User.keywords)).all()
            for u in users:
                if not user_is_active(u):
                    continue
                kws = [k.keyword for k in u.keywords]
                if not kws:
                    continue

                jobs: List[Dict[str, Any]] = []

                # Fetch from Freelancer
                jobs.extend(await fetch_freelancer(kws))

                # Fetch from Fiverr
                jobs.extend(await fetch_fiverr(kws))

                # Placeholders for other platforms
                await fetch_placeholder("PeoplePerHour")
                await fetch_placeholder("Malt")
                await fetch_placeholder("Workana")
                await fetch_placeholder("JobFind")
                await fetch_placeholder("Skywalker")
                await fetch_placeholder("Kariera")

                sent_ids = {js.job_id for js in db.query(JobSent).filter_by(user_id=u.id).all()}

                for job in jobs:
                    if job["id"] in sent_ids:
                        continue
                    # Save to DB
                    db.add(JobSent(user_id=u.id, job_id=job["id"], sent_at=now_utc()))
                    db.commit()

                    # Send to Telegram
                    try:
                        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                        from bot import build_application
                        app = build_application()
                        text = f"💼 *{job['title']}*\n\n{job['description'][:400]}..."
                        buttons = [
                            [InlineKeyboardButton("🔗 Open", url=affiliate_wrap(job["url"]))],
                        ]
                        markup = InlineKeyboardMarkup(buttons)
                        await app.bot.send_message(
                            chat_id=u.telegram_id,
                            text=text,
                            parse_mode="Markdown",
                            reply_markup=markup,
                            disable_web_page_preview=True,
                        )
                        logger.info(f"Sent job {job['id']} to {u.telegram_id}")
                    except Exception as e:
                        logger.warning(f"Error sending job {job['id']} to {u.telegram_id}: {e}")

            logger.info("Worker cycle complete.")
        except Exception as e:
            logger.exception(f"Worker loop error: {e}")
        finally:
            db.close()
        await asyncio.sleep(INTERVAL)


if __name__ == "__main__":
    asyncio.run(worker_loop())
