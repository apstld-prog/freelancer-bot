# worker.py
import os
import logging
import asyncio
import aiohttp
from datetime import datetime, timezone

from sqlalchemy.orm import joinedload

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, constants
from telegram.ext import Application

from db import SessionLocal, User, Keyword, JobSent, JobDismissed

from bot import build_application, now_utc

logging.basicConfig(level=logging.INFO, format="%(asctime)s [worker] %(levelname)s: %(message)s")
logger = logging.getLogger("worker")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
FREELANCER_REF = os.getenv("AFF_FREELANCER_ID", "")
FIVERR_REF = os.getenv("AFF_FIVERR_ID", "")
INTERVAL = int(os.getenv("WORKER_INTERVAL", "300"))  # seconds


# ---------------- Utils ----------------
def aff_wrap_freelancer(url: str) -> str:
    if FREELANCER_REF:
        if "?" in url:
            return f"{url}&referrer={FREELANCER_REF}"
        return f"{url}?f=give&referrer={FREELANCER_REF}"
    return url


def aff_wrap_fiverr(query: str) -> (str, str):
    if FIVERR_REF:
        base = f"https://go.fiverr.com/visit/?bta={FIVERR_REF}&brand=fiverrmarketplace"
        return f"{base}&landingPage=https://www.fiverr.com/search/gigs?query={query}", \
               f"https://www.fiverr.com/search/gigs?query={query}"
    return f"https://www.fiverr.com/search/gigs?query={query}", f"https://www.fiverr.com/search/gigs?query={query}"


def budget_to_usd(min_b: float, max_b: float, currency: str) -> str:
    if not min_b and not max_b:
        return "—"
    if currency and currency.upper() != "USD":
        # placeholder: δεν κάνουμε ακόμα real FX, το γυρνάμε raw
        return f"{min_b}–{max_b} {currency}"
    return f"{min_b}–{max_b} USD"


def job_keyboard(job_id: str, proposal_url: str, original_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💼 Proposal", url=proposal_url),
         InlineKeyboardButton("🔗 Original", url=original_url)],
        [InlineKeyboardButton("⭐ Keep", callback_data=f"save:{job_id}"),
         InlineKeyboardButton("🗑 Delete", callback_data=f"dismiss:{job_id}")]
    ])


# ---------------- Fetchers ----------------
async def fetch_freelancer(session, keywords: list[str]):
    results = []
    for kw in keywords:
        url = f"https://www.freelancer.com/api/projects/0.1/projects/active/?query={kw}&limit=5&compact=true&job_details=true&user_details=true&full_description=true&referrer={FREELANCER_REF}"
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.warning("Freelancer API non-200 for %s: %s", kw, resp.status)
                    continue
                data = await resp.json()
                for pr in data.get("result", {}).get("projects", []):
                    job_id = f"freelancer-{pr['id']}"
                    budget = pr.get("budget", {}) or {}
                    bmin = budget.get("minimum", 0.0)
                    bmax = budget.get("maximum", 0.0)
                    cur = budget.get("currency", {}).get("code", "USD")
                    results.append({
                        "id": job_id,
                        "title": pr.get("title"),
                        "description": pr.get("preview_description"),
                        "budget": budget_to_usd(bmin, bmax, cur),
                        "bids": pr.get("bid_stats", {}).get("bid_count", 0),
                        "posted": pr.get("submitdate"),
                        "url": aff_wrap_freelancer(f"https://www.freelancer.com/projects/{pr['seo_url']}"),
                        "original": f"https://www.freelancer.com/projects/{pr['seo_url']}",
                        "source": "Freelancer",
                        "type": pr.get("type", "Fixed"),
                    })
        except Exception as e:
            logger.warning("Freelancer fetch error: %s", e)
    return results


async def fetch_fiverr(session, keywords: list[str]):
    results = []
    for kw in keywords:
        prop, orig = aff_wrap_fiverr(kw)
        job_id = f"fiverr-{kw.lower()}-{int(datetime.now().timestamp())}"
        results.append({
            "id": job_id,
            "title": f"Fiverr services for {kw}",
            "description": f"Browse Fiverr gigs related to '{kw}'.",
            "budget": "—",
            "bids": "—",
            "posted": "0s ago",
            "url": prop,
            "original": orig,
            "source": "Fiverr",
            "type": "N/A",
        })
    return results


async def fetch_placeholder(name: str):
    logger.warning("%s fetcher not implemented yet.", name)
    return []


# ---------------- Worker Loop ----------------
async def worker_loop(app: Application):
    while True:
        db = SessionLocal()
        try:
            users = db.query(User).options(joinedload(User.keywords)).all()
            sent_total = 0
            async with aiohttp.ClientSession() as session:
                for u in users:
                    if u.is_blocked:
                        continue
                    # check license
                    now = now_utc()
                    if not ((u.trial_until and u.trial_until >= now) or (u.access_until and u.access_until >= now)):
                        continue

                    kws = [k.keyword for k in u.keywords]
                    if not kws:
                        continue

                    jobs = []
                    jobs += await fetch_freelancer(session, kws)
                    jobs += await fetch_fiverr(session, kws)
                    # placeholders for later
                    for name in ["PeoplePerHour", "Malt", "Workana", "JobFind", "Skywalker", "Kariera"]:
                        await fetch_placeholder(name)

                    for job in jobs:
                        dismissed = db.query(JobDismissed).filter_by(user_id=u.id, job_id=job["id"]).first()
                        if dismissed:
                            continue
                        already = db.query(JobSent).filter_by(user_id=u.id, job_id=job["id"]).first()
                        if already:
                            continue
                        db.add(JobSent(user_id=u.id, job_id=job["id"]))
                        db.commit()

                        text = (
                            f"🧑‍💻 *{job['title']}*\n\n"
                            f"👤 Source: *{job['source']}*\n"
                            f"🧾 Type: *{job['type']}*\n"
                            f"💰 Budget: *{job['budget']}*\n"
                            f"📨 Bids: *{job['bids']}*\n"
                            f"🕒 Posted: {job['posted']}\n\n"
                            f"{job['description']}"
                        )
                        try:
                            await app.bot.send_message(
                                chat_id=int(u.telegram_id),
                                text=text,
                                parse_mode=constants.ParseMode.MARKDOWN,
                                disable_web_page_preview=True,
                                reply_markup=job_keyboard(job["id"], job["url"], job["original"])
                            )
                            logger.info("Sent job %s to %s", job["id"], u.telegram_id)
                            sent_total += 1
                        except Exception as e:
                            logger.warning("Send failed to %s: %s", u.telegram_id, e)
            logger.info("Worker cycle complete. Sent %d messages.", sent_total)
        except Exception as e:
            logger.error("Worker loop error: %s", e, exc_info=True)
        finally:
            db.close()
        await asyncio.sleep(INTERVAL)


# ---------------- Entrypoint ----------------
async def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN not set")
    app = build_application()
    asyncio.create_task(worker_loop(app))
    await app.initialize()
    await app.start()
    logger.info("Worker running with bot started.")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
