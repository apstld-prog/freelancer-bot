#!/usr/bin/env python3
import asyncio
import logging
import os
from typing import Iterable, List, Tuple, Union

# project imports
from db import get_user_list
from platform_freelancer import fetch_freelancer_jobs
from utils import send_job_to_user

logger = logging.getLogger("worker.freelancer")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

# --- Interval resolution (PRIORITY) ---
# 1) FREELANCER_INTERVAL
# 2) FREELANCER_INTERVAL_SECONDS
# 3) CYCLE_SECONDS
# 4) default 60
FREELANCER_INTERVAL = int(
    os.getenv("FREELANCER_INTERVAL")
    or os.getenv("FREELANCER_INTERVAL_SECONDS")
    or os.getenv("CYCLE_SECONDS")
    or "60"
)

# Optional caps per run (δεν αλλάζουμε συμπεριφορά αν δεν υπάρχουν)
MAX_SEND_PER_LOOP = int(os.getenv("MAX_SEND_PER_LOOP", "0"))  # 0 = unlimited

# Απλό cache για να μην ξαναστείλουμε το ίδιο URL στον ίδιο χρήστη μέσα στη ζωή του worker
# { user_id: set(urls) }
sent_cache: dict[int, set[str]] = {}


def normalize_keywords(raw: Union[str, List[str], Tuple[str, ...], None]) -> List[str]:
    """Δέχεται keywords ως string με κόμματα ή ως λίστα/tuple και τα καθαρίζει."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        # string (π.χ. "logo, python ,react")
        items = [x.strip() for x in str(raw).replace(";", ",").split(",")]
    # καθάρισε κενά και διπλότυπα διατηρώντας σειρά
    seen = set()
    out: List[str] = []
    for x in items:
        if not x:
            continue
        low = x.lower()
        if low not in seen:
            seen.add(low)
            out.append(x)
    return out


def match_job(job: dict, keywords: List[str]) -> bool:
    """Επιστρέφει True αν ο τίτλος ή η περιγραφή περιέχει κάποιο από τα keywords."""
    if not keywords:
        return False
    title = (job.get("title") or "").lower()
    desc = (job.get("description") or job.get("snippet") or "").lower()
    text = f"{title}\n{desc}"
    return any(kw.lower() in text for kw in keywords)


def job_url_key(job: dict) -> str:
    """Μοναδικό κλειδί με βάση URL (ή fallback)."""
    return (
        job.get("url")
        or job.get("original_url")
        or job.get("affiliate_url")
        or f"{job.get('platform','freelancer')}::{job.get('id') or job.get('title')}"
    )


async def process_user(user_id: int, raw_keywords: Union[str, List[str], Tuple[str, ...], None]) -> None:
    """Fetch από Freelancer, φίλτρο με keywords, αποστολή στον χρήστη."""
    keywords = normalize_keywords(raw_keywords)
    if not keywords:
        logger.debug(f"[{user_id}] No keywords set. Skipping.")
        return

    try:
        jobs = await fetch_freelancer_jobs(",".join(keywords))
    except Exception as e:
        logger.exception(f"[{user_id}] fetch_freelancer_jobs failed: {e}")
        return

    if not jobs:
        logger.debug(f"[{user_id}] No jobs returned for keywords={keywords}")
        return

    # init cache for user
    sent = sent_cache.setdefault(user_id, set())

    sent_now = 0
    for job in jobs:
        # φίλτρο keywords στον τίτλο/περιγραφή
        if not match_job(job, keywords):
            continue

        key = job_url_key(job)
        if key in sent:
            continue

        # πρόσθεσε info για το keyword match (για να φαίνεται στο μήνυμα)
        job["_match_keywords"] = ", ".join(keywords)

        try:
            await send_job_to_user(user_id, job)
            sent.add(key)
            sent_now += 1
        except Exception as e:
            logger.warning(f"[{user_id}] Error sending job: {e}")

        if MAX_SEND_PER_LOOP and sent_now >= MAX_SEND_PER_LOOP:
            break


async def main_loop():
    logger.info(f"[Freelancer Worker] Interval={FREELANCER_INTERVAL}s (env priority OK)")
    while True:
        try:
            users: Iterable[Tuple[Union[int, str], Union[str, List[str], Tuple[str, ...]]]] = get_user_list()
            for uid, raw_keywords in users:
                try:
                    uid_int = int(uid)
                except Exception:
                    logger.warning(f"Invalid user id: {uid} (skipping)")
                    continue
                await process_user(uid_int, raw_keywords)
        except Exception as e:
            logger.error(f"[Freelancer Worker] main loop error: {e}")
        await asyncio.sleep(FREELANCER_INTERVAL)


if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("Freelancer worker stopped by user")
