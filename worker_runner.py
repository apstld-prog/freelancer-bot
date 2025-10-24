import logging
import asyncio
import httpx
import psycopg2
from datetime import datetime, timedelta, timezone
from platform_freelancer import fetch_freelancer_jobs
from platform_peopleperhour import fetch_pph_jobs
from platform_skywalker import fetch_skywalker_jobs
import os

log = logging.getLogger("worker")

DB_URL = os.getenv("DATABASE_URL")

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
            payload["reply_markup"] = {"inline_keyboard": [[{"text": "🔗 View Job", "url": str(url)}]]}

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
