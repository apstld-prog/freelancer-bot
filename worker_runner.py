import os
import time
import logging
import httpx
import asyncio
from datetime import datetime, timedelta
from bot import build_application
import platform_freelancer
import platform_peopleperhour

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "5254014824"))
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "120"))  # default 2 minutes
LOOKBACK_HOURS = int(os.getenv("LOOKBACK_HOURS", "48"))

async def send_jobs_directly(application, jobs, platform_name):
    """Send jobs directly via Telegram bot to ADMIN_CHAT_ID"""
    bot = application.bot
    for job in jobs:
        try:
            title = job.get("title") or "(no title)"
            desc = job.get("description") or ""
            budget = job.get("budget") or "?"
            currency = job.get("currency") or ""
            url = job.get("url") or "#"
            keyword = job.get("keyword") or ""

            msg = (
                f"📣 <b>{platform_name.upper()}</b>\n\n"
                f"🔹 <b>{title}</b>\n"
                f"{desc[:500]}...\n\n"
                f"💰 <b>Budget:</b> {budget} {currency}\n"
                f"🔍 <b>Keyword:</b> {keyword}\n\n"
                f"<a href='{url}'>View job</a>"
            )

            await bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=msg,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            await asyncio.sleep(1)
        except Exception as e:
            logging.error(f"[SEND_FAIL] {platform_name}: {e}")

async def worker_loop():
    """Main worker loop fetching from Freelancer + PPH"""
    logging.info("[Worker] Starting background process (internal send mode)...")
    app = build_application()
    async with app:
        await app.initialize()
        fresh_since = datetime.utcnow() - timedelta(hours=LOOKBACK_HOURS)

        while True:
            try:
                # FREELANCER
                logging.debug("Fetching from Freelancer...")
                freelancer_jobs = platform_freelancer.fetch()
                if freelancer_jobs:
                    logging.info(f"[FREELANCER] ✅ {len(freelancer_jobs)} new jobs")
                    await send_jobs_directly(app, freelancer_jobs, "freelancer")
                else:
                    logging.warning("[FREELANCER] No new jobs found.")

                # PEOPLEPERHOUR
                logging.debug("Fetching from PeoplePerHour...")
                pph_jobs = platform_peopleperhour.get_items()
                if pph_jobs:
                    logging.info(f"[PPH] ✅ {len(pph_jobs)} new jobs")
                    await send_jobs_directly(app, pph_jobs, "peopleperhour")
                else:
                    logging.warning("[PPH] No results fetched.")

                logging.info("[Worker] Cycle complete. Sleeping...")
                await asyncio.sleep(WORKER_INTERVAL)
            except Exception as e:
                logging.error(f"[Worker] Error in loop: {e}")
                await asyncio.sleep(WORKER_INTERVAL)

def main():
    asyncio.run(worker_loop())

if __name__ == "__main__":
    main()
