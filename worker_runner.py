import logging
import asyncio
import os
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("ADMIN_CHAT_ID")
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", 60))

async def fetch_jobs():
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            "https://www.freelancer.com/api/projects/0.1/projects/active/",
            params={
                "full_description": "false",
                "job_details": "false",
                "limit": 5,
                "sort_field": "time_submitted",
                "sort_direction": "desc",
                "query": "lighting,led"
            },
        )
        data = resp.json()
        return data.get("result", {}).get("projects", [])

async def send_message(job):
    text = f"📌 *{job['title']}*\n💰 {job.get('budget', {}).get('minimum', 0)} USD\n🌐 [View Original](https://www.freelancer.com/projects/{job['id']})"
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"},
        )

async def main_worker():
    while True:
        try:
            jobs = await fetch_jobs()
            logger.info(f"Fetched {len(jobs)} jobs")
            for job in jobs:
                await send_message(job)
        except Exception as e:
            logger.error(f"Worker error: {e}")
        await asyncio.sleep(WORKER_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main_worker())
