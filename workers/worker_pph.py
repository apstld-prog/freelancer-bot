#!/usr/bin/env python3
import asyncio
import logging
import os
from typing import Iterable, List, Tuple, Union
from db import get_user_list
from platform_peopleperhour import fetch_pph_jobs
from utils import send_job_to_user

logger = logging.getLogger("worker.pph")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

PPH_INTERVAL = int(
    os.getenv("PPH_INTERVAL")
    or os.getenv("PPH_INTERVAL_SECONDS")
    or os.getenv("CYCLE_SECONDS")
    or "300"
)

sent_cache: dict[int, set[str]] = {}


def normalize_keywords(raw: Union[str, List[str], Tuple[str, ...], None]) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        items = [x.strip() for x in str(raw).replace(";", ",").split(",")]
    seen = set()
    out = []
    for x in items:
        if not x:
            continue
        low = x.lower()
        if low not in seen:
            seen.add(low)
            out.append(x)
    return out


def match_job(job: dict, keywords: List[str]) -> bool:
    title = (job.get("title") or "").lower()
    desc = (job.get("description") or "").lower()
    text = f"{title}\n{desc}"
    return any(k.lower() in text for k in keywords)


def job_url_key(job: dict) -> str:
    return (
        job.get("url")
        or job.get("original_url")
        or job.get("affiliate_url")
        or f"pph::{job.get('id') or job.get('title')}"
    )


async def process_user(user_id: int, raw_keywords: Union[str, List[str], Tuple[str, ...], None]) -> None:
    keywords = normalize_keywords(raw_keywords)
    if not keywords:
        return
    try:
        jobs = await fetch_pph_jobs(",".join(keywords))
    except Exception as e:
        logger.error(f"[{user_id}] fetch_pph_jobs failed: {e}")
        return

    sent = sent_cache.setdefault(user_id, set())
    for job in jobs:
        if not match_job(job, keywords):
            continue
        key = job_url_key(job)
        if key in sent:
            continue
        job["_match_keywords"] = ", ".join(keywords)
        try:
            await send_job_to_user(user_id, job)
            sent.add(key)
        except Exception as e:
            logger.warning(f"[{user_id}] Error sending job: {e}")


async def main_loop():
    logger.info(f"[PPH Worker] Interval={PPH_INTERVAL}s (env priority OK)")
    while True:
        try:
            users: Iterable[Tuple[int, str]] = get_user_list()
            for uid, raw_keywords in users:
                await process_user(int(uid), raw_keywords)
        except Exception as e:
            logger.error(f"[PPH Worker] main loop error: {e}")
        await asyncio.sleep(PPH_INTERVAL)


if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("PPH worker stopped by user")
