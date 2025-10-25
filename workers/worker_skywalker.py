import asyncio
import logging
import os
import json
from platform_skywalker import fetch_skywalker_jobs
from utils import send_job_to_user

logger = logging.getLogger("worker_skywalker")

SKYWALKER_INTERVAL = int(os.getenv("SKYWALKER_INTERVAL", "300"))
TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
    or os.getenv("BOT_TOKEN")
)


def load_users():
    with open("data/users.json", encoding="utf-8") as f:
        return [u for u in json.load(f) if u.get("active")]


def load_keywords_for_user(user_id):
    with open("data/keywords.json", encoding="utf-8") as f:
        data = json.load(f)
        return [k["keyword"] for k in data if k["user_id"] == user_id]


async def process_user(user, keywords):
    for kw in keywords:
        jobs = await fetch_skywalker_jobs(kw)
        for job in jobs:
            await send_job_to_user(user["telegram_id"], job)


async def main_loop():
    logger.info("[Skywalker Worker] Started.")
    while True:
        users = load_users()
        for user in users:
            keywords = load_keywords_for_user(user["user_id"])
            await process_user(user, keywords)
        await asyncio.sleep(SKYWALKER_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main_loop())
