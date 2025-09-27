import os
import logging
import asyncio
import hashlib
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional

import aiohttp
import feedparser
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from db import SessionLocal, User, Keyword, JobSent, JobFingerprint

# -------------------- Config --------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
AFFILIATE_PREFIX = os.getenv("AFFILIATE_PREFIX", "https://affiliate-network.com/?url=")
FETCH_INTERVAL_SEC = int(os.getenv("FETCH_INTERVAL_SEC", "60"))

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is not set.")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [worker] %(levelname)s: %(message)s")
logger = logging.getLogger("freelancer-worker")
bot = Bot(BOT_TOKEN)

# --- ENV feeds (comma-separated URLs) ---
# International
FREELANCER_RSS_URLS = [u.strip() for u in os.getenv("FREELANCER_RSS_URLS", "").split(",") if u.strip()]
PPH_RSS_URLS         = [u.strip() for u in os.getenv("PPH_RSS_URLS", "").split(",") if u.strip()]
MALT_RSS_URLS        = [u.strip() for u in os.getenv("MALT_RSS_URLS", "").split(",") if u.strip()]
WORKANA_JSON_URLS    = [u.strip() for u in os.getenv("WORKANA_JSON_URLS", "").split(",") if u.strip()]

# Greece
JOBFIND_RSS_URLS     = [u.strip() for u in os.getenv("JOBFIND_RSS_URLS", "").split(",") if u.strip()]
SKYWALKER_RSS_URLS   = [u.strip() for u in os.getenv("SKYWALKER_RSS_URLS", "").split(",") if u.strip()]
KARIERA_RSS_URLS     = [u.strip() for u in os.getenv("KARIERA_RSS_URLS", "").split(",") if u.strip()]

# --- Source priority (affiliate first, then rank) ---
SOURCE_PRIORITY = {
    # source: (has_affiliate, rank)
    "freelancer":     (True,  1),
    "peopleperhour":  (True,  2),
    "malt":           (False, 3),
    "workana":        (False, 4),
    "jobfind":        (False, 5),
    "skywalker":      (False, 6),
    "kariera":        (False, 7),
}

# --- Source -> region (used by secondary country filter) ---
SOURCE_REGION = {
    "freelancer": "GLOBAL",
    "peopleperhour": "UK",
    "malt": "FR",
    "workana": "ES",
    "jobfind": "GR",
    "skywalker": "GR",
    "kariera": "GR",
}

# -------------------- Helpers --------------------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def affiliate_wrap(url: str) -> str:
    return f"{AFFILIATE_PREFIX}{url}" if AFFILIATE_PREFIX else url

def normalize_text(s: str) -> str:
    return " ".join((s or "").lower().split())

def make_fingerprint(title: str, description: str) -> str:
    base = normalize_text((title or "") + " " + (description or ""))
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:40]

def user_is_active(u: User) -> bool:
    # access check (trial or license and not blocked)
    if getattr(u, "is_blocked", False):
        return False
    t = now_utc()
    if getattr(u, "access_until", None) and u.access_until >= t:
        return True
    if getattr(u, "trial_until", None) and u.trial_until >= t:
        return True
    return False

# ------------- HTTP helpers / adapters -------------
async def fetch_text(session: aiohttp.ClientSession, url: str) -> Optional[str]:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
            if r.status == 200:
                return await r.text()
            logger.warning("Non-200 from %s: %s", url, r.status)
    except Exception as e:
        logger.warning("Error fetching %s: %s", url, e)
    return None

async def fetch_rss_list(session: aiohttp.ClientSession, urls: List[str], source: str, country_hint: str) -> List[Dict]:
    out: List[Dict] = []
    for url in urls:
        text = await fetch_text(session, url)
        if not text:
            continue
        feed = feedparser.parse(text)
        for e in feed.entries:
            title = e.get("title", "").strip()
            link = (e.get("link") or e.get("id") or "").strip()
            desc = (e.get("summary") or e.get("description") or "").strip()
            if not title or not link:
                continue
            # Try to pull a country tag if exists; else use hint
            country = (e.get("tags", [{}])[0].get("term") if e.get("tags") else None) or country_hint
            out.append({
                "source": source,
                "id": e.get("id") or link,
                "title": title,
                "url": link,
                "description": desc,
                "country": country or "GLOBAL",
            })
    return out

async def fetch_json_list(session: aiohttp.ClientSession, urls: List[str], source: str, country_hint: str) -> List[Dict]:
    out: List[Dict] = []
    for url in urls:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status != 200:
                    logger.warning("Non-200 JSON from %s: %s", url, r.status); continue
                data = await r.json()
        except Exception as e:
            logger.warning("Error fetching JSON %s: %s", url, e); continue

        items = data if isinstance(data, list) else data.get("items") or data.get("results") or []
        for it in items:
            title = (it.get("title") or it.get("name") or "").strip()
            link = (it.get("url") or it.get("link") or "").strip()
            desc = (it.get("description") or it.get("summary") or "")
            country = (it.get("country") or it.get("locale") or country_hint) or "GLOBAL"
            if not title or not link:
                continue
            out.append({
                "source": source,
                "id": it.get("id") or link,
                "title": title,
                "url": link,
                "description": desc,
                "country": country,
            })
    return out

# --- source specific ---
async def fetch_from_freelancer(session) -> List[Dict]:
    if not FREELANCER_RSS_URLS:
        return []
    return await fetch_rss_list(session, FREELANCER_RSS_URLS, "freelancer", "GLOBAL")

async def fetch_from_pph(session) -> List[Dict]:
    if not PPH_RSS_URLS:
        return []
    return await fetch_rss_list(session, PPH_RSS_URLS, "peopleperhour", "UK")

async def fetch_from_malt(session) -> List[Dict]:
    if not MALT_RSS_URLS:
        return []
    return await fetch_rss_list(session, MALT_RSS_URLS, "malt", "FR")

async def fetch_from_workana(session) -> List[Dict]:
    if not WORKANA_JSON_URLS:
        return []
    return await fetch_json_list(session, WORKANA_JSON_URLS, "workana", "ES")

# Greece
async def fetch_from_jobfind(session) -> List[Dict]:
    if not JOBFIND_RSS_URLS:
        return []
    return await fetch_rss_list(session, JOBFIND_RSS_URLS, "jobfind", "GR")

async def fetch_from_skywalker(session) -> List[Dict]:
    if not SKYWALKER_RSS_URLS:
        return []
    return await fetch_rss_list(session, SKYWALKER_RSS_URLS, "skywalker", "GR")

async def fetch_from_kariera(session) -> List[Dict]:
    if not KARIERA_RSS_URLS:
        return []
    return await fetch_rss_list(session, KARIERA_RSS_URLS, "kariera", "GR")

# ------------- Aggregator -------------
async def fetch_jobs() -> List[Dict]:
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            fetch_from_freelancer(session),
            fetch_from_pph(session),
            fetch_from_malt(session),
            fetch_from_workana(session),
            fetch_from_jobfind(session),
            fetch_from_skywalker(session),
            fetch_from_kariera(session),
            return_exceptions=False,
        )
    jobs: List[Dict] = []
    for lst in results:
        jobs.extend(lst)
    return jobs

# ------------- Canonical / dedup -------------
def choose_canonical(existing_row: JobFingerprint, candidate: Dict) -> Optional[Dict]:
    cand_src = candidate["source"]
    cand_aff, cand_rank = SOURCE_PRIORITY.get(cand_src, (False, 99))
    ex_aff, ex_rank = SOURCE_PRIORITY.get(existing_row.source, (existing_row.has_affiliate, 99))
    # Prefer affiliate, then lower rank (higher priority)
    if cand_aff and not ex_aff:
        return candidate
    if (cand_aff == ex_aff) and (cand_rank < ex_rank):
        return candidate
    return None

def match_job_to_user(job: Dict, user: User, keywords: List[Keyword]) -> bool:
    # primary: by keywords
    text = normalize_text(job.get("title", "") + " " + job.get("description", ""))
    if not any(kw.keyword.lower() in text for kw in keywords):
        return False
    # country filter (accept job.country OR platform region)
    if user.countries and user.countries != "ALL":
        allowed = {c.strip().upper() for c in (user.countries or "").split(",")}
        job_cc = (job.get("country") or "GLOBAL").upper()
        src_cc = SOURCE_REGION.get(job.get("source",""), "GLOBAL").upper()
        if job_cc not in allowed and src_cc not in allowed:
            return False
    return True

# ------------- Notifications (expiry) -------------

def _notify_key(user_id: int, tag: str, day: datetime) -> str:
    # e.g. NOTIFY-EXPIRING-2025-09-27 or NOTIFY-EXPIRED-2025-09-27
    return f"NOTIFY-{tag}-{day.strftime('%Y-%m-%d')}-USR-{user_id}"

async def maybe_notify_expiry(user: User):
    """
    Στέλνει ειδοποίηση λήξης/επικείμενης λήξης μία φορά την ημέρα,
    χρησιμοποιώντας το JobSent ως μηχανισμό dedup (job_id unique).
    """
    db = SessionLocal()
    try:
        today = now_utc().date()
        # Υπολόγισε το πλησιέστερο expiry (trial ή license)
        expiries = [dt for dt in [getattr(user, "access_until", None), getattr(user, "trial_until", None)] if dt]
        target = min(expiries) if expiries else None
        if not target:
            return

        remaining = (target - now_utc()).total_seconds()
        # expiring soon (<=24h and >0)
        if 0 < remaining <= 24 * 3600:
            key = _notify_key(user.id, "EXPIRING", datetime(today.year, today.month, today.day, tzinfo=timezone.utc))
            # αν έχει σταλεί σήμερα, μην το ξαναστείλεις
            if not db.query(JobSent).filter_by(user_id=user.id, job_id=key).first():
                txt = (
                    "⏳ *Your access expires soon (≤ 24h).* \n"
                    "If you need more time, send `/contact I need more access`."
                )
                await bot.send_message(chat_id=user.telegram_id, text=txt, parse_mode="Markdown")
                db.add(JobSent(user_id=user.id, job_id=key)); db.commit()
            return

        # expired (<=0)
        if remaining <= 0:
            key = _notify_key(user.id, "EXPIRED", datetime(today.year, today.month, today.day, tzinfo=timezone.utc))
            if not db.query(JobSent).filter_by(user_id=user.id, job_id=key).first():
                txt = (
                    "🔒 *Your access has expired.*\n"
                    "Use `/status` to see details or `/contact I need access` to reach the admin."
                )
                await bot.send_message(chat_id=user.telegram_id, text=txt, parse_mode="Markdown")
                db.add(JobSent(user_id=user.id, job_id=key)); db.commit()
    finally:
        db.close()

# ------------- Sending jobs -------------
async def send_job(user: User, job: Dict, canonical_url: str, fingerprint: str):
    # Only send if user has active trial/license
    if not user_is_active(user):
        # Αλλά στείλε πιθανή ειδοποίηση λήξης/λήξης
        await maybe_notify_expiry(user)
        return

    db = SessionLocal()
    try:
        if db.query(JobSent).filter_by(user_id=user.id, job_id=fingerprint).first():
            return

        aff_url = affiliate_wrap(canonical_url)

        buttons = [
            [InlineKeyboardButton("⭐ Save", callback_data=f"save:{fingerprint}"),
             InlineKeyboardButton("🙈 Dismiss", callback_data=f"dismiss:{fingerprint}")],
            [InlineKeyboardButton("💼 Proposal", url=aff_url),
             InlineKeyboardButton("🔗 Original", url=aff_url)],
        ]
        keyboard = InlineKeyboardMarkup(buttons)

        desc = (job.get("description") or "").strip()
        if len(desc) > 300:
            desc = desc[:300] + "..."

        text = f"💼 *{job['title']}*\n\n{desc}\n\n🔗 [View Job]({aff_url})"
        await bot.send_message(
            chat_id=user.telegram_id, text=text, reply_markup=keyboard,
            parse_mode="Markdown", disable_web_page_preview=True,
        )

        db.add(JobSent(user_id=user.id, job_id=fingerprint)); db.commit()
    finally:
        db.close()

# ------------- Processing -------------
async def process_jobs():
    jobs = await fetch_jobs()
    if not jobs:
        return

    db = SessionLocal()
    try:
        # Update/insert canonical per fingerprint
        for job in jobs:
            fp = make_fingerprint(job.get("title",""), job.get("description",""))
            url = job.get("url","")
            src = job.get("source","unknown")
            has_aff = SOURCE_PRIORITY.get(src, (False, 99))[0]

            row = db.query(JobFingerprint).filter_by(fingerprint=fp).first()
            if not row:
                row = JobFingerprint(
                    fingerprint=fp,
                    canonical_url=url,
                    source=src,
                    title=job.get("title"),
                    country=job.get("country"),
                    has_affiliate=has_aff,
                )
                db.add(row); db.commit()
            else:
                better = choose_canonical(row, job)
                if better:
                    row.canonical_url = better["url"]
                    row.source = better["source"]
                    row.has_affiliate = SOURCE_PRIORITY.get(row.source, (False,99))[0]
                    row.title = better.get("title", row.title)
                    row.country = better.get("country", row.country)
                    db.commit()

        # Deliver to users based on canonical entries
        users = db.query(User).all()
        for row in db.query(JobFingerprint).all():
            # Find one representative job with same fingerprint (for text/desc)
            original = next(
                (j for j in jobs if make_fingerprint(j.get("title",""), j.get("description","")) == row.fingerprint),
                None
            )
            if not original:
                continue
            for user in users:
                kws = db.query(Keyword).filter_by(user_id=user.id).all()
                if kws and match_job_to_user(original, user, kws):
                    await send_job(user, original, row.canonical_url, row.fingerprint)

        # Additionally, check expiry notifications for all users (once per loop)
        for user in users:
            if not user_is_active(user):
                await maybe_notify_expiry(user)
    finally:
        db.close()

# ------------- Loop -------------
async def worker_loop():
    logger.info("Worker loop running every %ss", FETCH_INTERVAL_SEC)
    while True:
        try:
            await process_jobs()
        except Exception as e:
            logger.exception(f"Error in worker loop: {e}")
        await asyncio.sleep(FETCH_INTERVAL_SEC)

def main():
    asyncio.run(worker_loop())

if __name__ == "__main__":
    main()
