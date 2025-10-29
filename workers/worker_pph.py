import os
import sys
import time
import logging
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from platform_pph import fetch_pph_jobs
from db_keywords import get_all_user_keywords
from currency_usd import usd_line
from utils import send_job_to_user

logger = logging.getLogger("worker_pph")

def _short(text: str, n: int = 400) -> str:
    if not text:
        return ""
    text = text.strip()
    return text if len(text) <= n else (text[:n] + "...")

def _build_message(job: dict) -> str:
    title = job.get("title") or "N/A"
    desc = _short(job.get("description") or "")
    kw = job.get("matched_keyword") or "N/A"
    cur = (job.get("budget_currency") or "USD").upper()
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
        "🌍 Source: PeoplePerHour",
        f"🔑 Match: {kw}",
        f"🕒 Posted: {posted_ago}",
        "",
        f"📝 {desc}" if desc else "",
    ]
    return "\n".join([l for l in lines if l != ""])

def parse_dt(v):
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(v)
    except Exception:
        return datetime.utcnow()

def main():
    logging.basicConfig(level=logging.INFO)
    logger.info("[PeoplePerHour Worker] Started")
    while True:
        try:
            users = get_all_user_keywords()
            for user_id, kws in users.items():
                if not kws:
                    continue
                jobs = fetch_pph_jobs(kws)
                now = datetime.utcnow()
                jobs = [
                    j for j in jobs
                    if not j.get("created_at") or (
                        now.replace(tzinfo=None) - parse_dt(j["created_at"]).replace(tzinfo=None)
                    ) <= timedelta(hours=48)
                ]
                for job in jobs:
                    msg = _build_message(job)
                    import asyncio
                    try:
                        asyncio.run(send_job_to_user(None, int(user_id), msg, job))
                    except RuntimeError:
                        pass
            time.sleep(60)
        except Exception as e:
            logger.exception("[PeoplePerHour Worker] Error: %s", e)
            time.sleep(120)

if __name__ == "__main__":
    main()
