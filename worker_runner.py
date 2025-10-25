import asyncio
import logging
import os
import inspect
from typing import Iterable, List, Dict, Set, Any
from telegram import Bot

from db import get_user_list
from platform_freelancer import fetch_freelancer_jobs
from platform_peopleperhour import fetch_pph_jobs
from utils import send_job_to_user

logger = logging.getLogger("worker")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "180"))
TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
    or os.getenv("BOT_TOKEN")
)

# ανά χρήστη κρατάμε σύνολο από URLs που έχουν σταλεί
sent_cache: Dict[int, Set[str]] = {}


def normalize_keywords(raw) -> List[str]:
    """
    Δέχεται string (π.χ. 'logo, lighting') ή λίστα (['logo','lighting'])
    και επιστρέφει καθαρή λίστα keywords.
    """
    if raw is None:
        return []
    # από DB μπορεί να έρθει ήδη list/tuple/set
    if isinstance(raw, (list, tuple, set)):
        items: List[str] = []
        for item in raw:
            if isinstance(item, str):
                # υποστήριξε και περίπτωση 'a,b' μέσα σε element
                parts = [p.strip() for p in item.split(",")]
                items.extend([p for p in parts if p])
        return [k for k in items if k]
    # plain string
    if isinstance(raw, str):
        return [k.strip() for k in raw.split(",") if k.strip()]
    # οτιδήποτε άλλο -> κάν’ το string
    return [str(raw).strip()] if str(raw).strip() else []


async def maybe_call(func, *args, **kwargs) -> Any:
    """
    Αν η platform_* είναι async, κάνε await. Αν είναι sync, εκτέλεσε κανονικά.
    """
    try:
        result = func(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result
    except Exception as e:
        logger.exception("Error calling %s: %s", getattr(func, "__name__", func), e)
        return []


def add_to_cache(user_id: int, url: str) -> bool:
    """
    Επιστρέφει True αν είναι νέο (να σταλεί), False αν το έχουμε ξαναστείλει.
    """
    if not url:
        return False
    s = sent_cache.setdefault(user_id, set())
    if url in s:
        return False
    s.add(url)
    return True


async def process_user(bot: Bot, user_id: int, keywords: Iterable[str]) -> None:
    for kw in keywords:
        # Freelancer
        f_jobs = await maybe_call(fetch_freelancer_jobs, kw)
        for job in f_jobs or []:
            job.setdefault("keyword", kw)
            url = job.get("url") or job.get("original_url") or job.get("affiliate_url")
            if add_to_cache(user_id, url):
                try:
                    await asyncio.to_thread(send_job_to_user, bot, user_id, job)
                except Exception as e:
                    logger.error("[Worker] Error sending job to %s: %s", user_id, e)

        # PeoplePerHour
        pph_jobs = await maybe_call(fetch_pph_jobs, kw)
        for job in pph_jobs or []:
            job.setdefault("keyword", kw)
            url = job.get("url") or job.get("original_url") or job.get("affiliate_url")
            if add_to_cache(user_id, url):
                try:
                    await asyncio.to_thread(send_job_to_user, bot, user_id, job)
                except Exception as e:
                    logger.error("[Worker] Error sending job to %s: %s", user_id, e)


async def main_loop():
    if not TOKEN:
        logger.error("[Worker] ERROR: Missing TELEGRAM_BOT_TOKEN / TELEGRAM_TOKEN / BOT_TOKEN.")
        return
    logger.info("[Worker] Using Telegram token from environment. Interval=%ss", WORKER_INTERVAL)
    bot = Bot(TOKEN)

    while True:
        try:
            # DB πρέπει να επιστρέφει π.χ. [(5254014824, 'logo, lighting'), (7916253053, ['photometric','led'])]
            rows = get_user_list() or []
            for row in rows:
                # υποστηρίζουμε είτε tuple (user_id, keywords) είτε dict
                if isinstance(row, dict):
                    user_id = int(row.get("user_id"))
                    raw_keywords = row.get("keywords")
                else:
                    # αναμένουμε (user_id, keywords)
                    user_id = int(row[0])
                    raw_keywords = row[1]

                kws = normalize_keywords(raw_keywords)
                if not kws:
                    continue

                await process_user(bot, user_id, kws)

        except Exception as e:
            logger.error("[Worker] Error in main loop: %s", e)

        await asyncio.sleep(WORKER_INTERVAL)


if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        pass
