import logging
import asyncio
import httpx
import psycopg2
import os
import time
from datetime import datetime, timedelta, timezone

from platform_freelancer import fetch_freelancer_jobs
from platform_peopleperhour import fetch_pph_jobs
from platform_skywalker import fetch_skywalker_jobs

log = logging.getLogger("worker")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

DB_URL = os.getenv("DATABASE_URL")
BOT_TOKEN = (
    os.getenv("BOT_TOKEN")
    or os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
)


def get_connection():
    return psycopg2.connect(DB_URL)


async def send_job(bot_token, chat_id, job):
    try:
        title = job.get("title", "Untitled")
        desc = job.get("description", "")[:500]
        src = job.get("source", "")
        url = job.get("affiliate_url") or job.get("original_url")
        budget = job.get("budget_amount")
        currency = job.get("budget_currency")

        if budget and currency:
            budget_str = f"{budget} {currency}"
        elif budget:
            budget_str = f"{budget}"
        else:
            budget_str = "N/A"

        text = f"💼 *{title}*\n\n{desc}\n\n🌐 Source: {src}\n💰 Budget: {budget_str}"

        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }

        if url:
            payload["reply_markup"] = {
                "inline_keyboard": [[{"text": "🔗 View Job", "url": str(url)}]]
            }

        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json=payload,
                timeout=20,
            )
            if r.status_code != 200:
                log.warning(f"send_job error {r.status_code}: {r.text}")

    except Exception as e:
        log.warning(f"send_job exception: {e}")


# ✅ Helper: safely await if coroutine
async def ensure_awaitable(func_result):
    if asyncio.iscoroutine(func_result):
        return await func_result
    return func_result


async def process_user(user):
    try:
        user_id = user[0]
        keywords = user[1]
        if not keywords:
            return

        kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
        log.info(f"[Worker] Fetching for user {user_id} (kw={','.join(kw_list)})")

        # Unified handling for async/sync functions
        jobs_f = await ensure_awaitable(fetch_freelancer_jobs(kw_list))
        jobs_p = await ensure_awaitable(fetch_pph_jobs(kw_list))
        jobs_s = await ensure_awaitable(fetch_skywalker_jobs(kw_list))

        total = (jobs_f or []) + (jobs_p or []) + (jobs_s or [])
        log.info(f"[Worker] Total jobs merged: {len(total)}")

        for job in total[:10]:
            await send_job(BOT_TOKEN, user_id, job)

        log.info(f"[Worker] ✅ Sent {len(total[:10])} jobs → {user_id}")

    except Exception as e:
        log.error(f"[Worker] Error processing user {user}: {e}")


async def main_loop():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, keywords FROM "user";')
    users = cur.fetchall()
    cur.close()
    conn.close()

    log.info(f"[Worker] Total users: {len(users)}")
    for user in users:
        await process_user(user)


if __name__ == "__main__":
    log.info("[Worker] Starting background process...")
    try:
        while True:
            asyncio.run(main_loop())
            log.info("[Worker] Cycle complete. Sleeping...")
            time.sleep(int(os.getenv("WORKER_INTERVAL", "180")))
    except KeyboardInterrupt:
        log.info("[Worker] Stopped manually.")
    except Exception as e:
        log.error(f"[Worker main_loop error] {e}")
