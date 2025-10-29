
import os, sys, asyncio, logging
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from platform_freelancer import fetch_freelancer_jobs
from utils import send_job_to_user, time_ago, convert_to_usd
from db import get_user_keywords

logger = logging.getLogger("worker_freelancer")

def _short(text: str, n: int = 400) -> str:
    if not text: return ""
    text = text.strip()
    return text if len(text) <= n else (text[:n] + "...")

def _build_message(job: dict) -> str:
    title = job.get("title") or "N/A"
    desc = _short(job.get("description") or "")
    kw = job.get("matched_keyword") or job.get("keyword") or "N/A"
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

    usd_value = convert_to_usd(min_amt or avg_amt, cur)
    usd_line = f"   ~ ${usd_value} USD" if usd_value not in (None, "N/A") else ""
    posted_ago = job.get("posted_ago") or time_ago(job.get("created_at"))

    lines = [
        f"💼 {title}",
        f"💰 Budget: {main_budget}{usd_line}",
        "🌍 Source: Freelancer",
        f"🔑 Match: {kw}",
        f"🕒 Posted: {posted_ago}",
        "",
        f"📝 {desc}" if desc else "",
    ]
    return "\n".join([l for l in lines if l != ""])

def _parse_dt(v):
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    try:
        # accept "2025-10-29T18:10:00Z" etc.
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None

async def main():
    logging.basicConfig(level=logging.INFO)
    logger.info("[Freelancer Worker] Started")
    while True:
        try:
            user_map = await get_user_keywords()  # {telegram_id: [kw,...]}
            if not user_map:
                await asyncio.sleep(60); continue

            # Single API call per cycle based on union of all keywords
            all_kws = sorted({k.lower() for kws in user_map.values() for k in kws})[:50]
            jobs = fetch_freelancer_jobs(all_kws)

            # freshness filter (<=48h)
            now = datetime.now(timezone.utc)
            fresh = []
            for j in jobs:
                dt = _parse_dt(j.get("created_at"))
                if (dt is None) or ((now - dt).total_seconds() <= 48*3600):
                    fresh.append(j)
            jobs = fresh

            # per-user match & send
            for tid, kws in user_map.items():
                low = [k.lower() for k in kws]
                for job in jobs:
                    text = (job.get("title","") + " " + job.get("description","")).lower()
                    mk = next((k for k in low if k in text), None)
                    if not mk: 
                        continue
                    job['matched_keyword'] = mk
                    message = _build_message(job)
                    await send_job_to_user(None, int(tid), message, job)

            await asyncio.sleep(int(os.getenv("FREELANCER_INTERVAL", "60")))
        except Exception as e:
            logger.exception("[Freelancer Worker] Error: %s", e)
            await asyncio.sleep(120)

if __name__ == "__main__":
    asyncio.run(main())
