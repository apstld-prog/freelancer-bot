
import os, sys, asyncio, logging
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from platform_peopleperhour import fetch_pph_jobs
from utils import send_job_to_user, time_ago, convert_to_usd
from db import get_user_keywords

logger = logging.getLogger("worker_pph")

def _short(text: str, n: int = 400) -> str:
    if not text: return ""
    text = text.strip()
    return text if len(text) <= n else (text[:n] + "...")

def _build_message(job: dict) -> str:
    title = job.get("title") or "N/A"
    desc = _short(job.get("description") or "")
    kw = job.get("matched_keyword") or job.get("keyword") or "N/A"
    cur = (job.get("budget_currency") or job.get("currency") or "USD").upper()
    amt = job.get("budget_amount") or job.get("budget")
    main_budget = f"{amt} {cur}" if amt else f"N/A {cur}"
    usd_value = convert_to_usd(amt, cur)
    usd_line = f"   ~ ${usd_value} USD" if usd_value not in (None, "N/A") else ""
    posted_ago = job.get("posted_ago") or time_ago(job.get("created_at"))

    lines = [
        f"💼 {title}",
        f"💰 Budget: {main_budget}{usd_line}",
        "🌍 Source: PeoplePerHour",
        f"🔑 Match: {kw}",
        f"🕒 Posted: {posted_ago}",
        "",
        f"📝 {desc}" if desc else "",
    ]
    return "\n".join([l for l in lines if l != ""])

async def main():
    logging.basicConfig(level=logging.INFO)
    logger.info("[PeoplePerHour Worker] Started")
    while True:
        try:
            user_map = await get_user_keywords()  # {telegram_id: [kw,...]}
            if not user_map:
                await asyncio.sleep(300); continue

            all_kws = sorted({k.lower() for kws in user_map.values() for k in kws})[:50]
            jobs = fetch_pph_jobs(all_kws)

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

            await asyncio.sleep(int(os.getenv("PPH_INTERVAL", "300")))
        except Exception as e:
            logger.exception("[PeoplePerHour Worker] Error: %s", e)
            await asyncio.sleep(120)

if __name__ == "__main__":
    asyncio.run(main())
