import os
import sys
import time
import logging

# Ensure project root in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from platform_skywalker import fetch_skywalker_jobs
from db_keywords import get_all_user_keywords
from currency_usd import usd_line
from utils import send_job_to_user

logger = logging.getLogger("worker_skywalker")

def _short(text: str, n: int = 400) -> str:
    if not text:
        return ""
    text = text.strip()
    return text if len(text) <= n else (text[:n] + "...")

def _build_message(job: dict) -> str:
    title = job.get("title") or "N/A"
    desc = _short(job.get("description") or "")
    kw = job.get("matched_keyword") or "N/A"
    cur = (job.get("budget_currency") or "EUR").upper()  # συνήθως GR/EUR

    min_amt = job.get("budget_min")
    max_amt = job.get("budget_max")
    avg_amt = job.get("budget_amount")

    if min_amt and max_amt:
        main_budget = f"{min_amt}–{max_amt} {cur}"
    elif avg_amt:
        main_budget = f"{avg_amt} {cur}"
    else:
        main_budget = f"N/A {cur}"

    usd = usd_line(min_amt or avg_amt, max_amt, cur)
    budget_line = f"💰 Budget: {main_budget}"
    if usd:
        budget_line += f"   {usd}"

    posted_ago = job.get("posted_ago") or "N/A"

    lines = [
        f"💼 {title}",
        budget_line,
        "🌍 Source: Skywalker",
        f"🔑 Match: {kw}",
        f"🕒 Posted: {posted_ago}",
        "",
        f"📝 {desc}" if desc else "",
    ]
    return "\n".join([l for l in lines if l != ""])

def main():
    logging.basicConfig(level=logging.INFO)
    logger.info("[Skywalker Worker] Started")
    while True:
        try:
            users = get_all_user_keywords()
            for user_id, kws in users.items():
                if not kws:
                    continue
                jobs = fetch_skywalker_jobs(kws)
                for job in jobs:
                    msg = _build_message(job)
                    import asyncio
                    try:
                        asyncio.run(send_job_to_user(None, int(user_id), msg, job))
                    except RuntimeError:
                        pass
            time.sleep(300)
        except Exception as e:
            logger.exception("[Skywalker Worker] Error: %s", e)
            time.sleep(120)

if __name__ == "__main__":
    main()
