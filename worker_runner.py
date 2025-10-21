import os
import time
import asyncio
import logging
import httpx
from datetime import datetime, timezone
from sqlalchemy import text
from db import get_session
from db_events import record_event
from db_keywords import list_keywords
from config import WORKER_INTERVAL

from platform_freelancer import fetch_freelancer_jobs
from platform_peopleperhour import fetch_pph_graphql, fetch_pph_html
from platform_skywalker import fetch_skywalker_jobs
from platform_kariera import fetch_kariera_jobs

log = logging.getLogger("worker")
logging.basicConfig(level=logging.INFO)

# =====================================================
# UTILITIES
# =====================================================
async def send_job(bot, chat_id, job):
    """Send formatted job card to Telegram user."""
    try:
        title = job.get("title", "").strip()
        desc = (job.get("description") or "").strip()
        budget = job.get("budget", "")
        match_kw = job.get("match", "")
        url = job.get("original_url", "")
        source = job.get("source", "Unknown")

        text_msg = (
            f"<b>{title}</b>\n"
            f"<b>Budget:</b> {budget}\n"
            f"<b>Source:</b> {source}\n"
            f"<b>Match:</b> {match_kw}\n"
            f"{desc}\n"
        )

        kb = {
            "inline_keyboard": [
                [
                    {"text": "📄 Proposal", "url": url},
                    {"text": "🔗 Original", "url": url},
                ],
                [
                    {"text": "⭐ Save", "callback_data": "job:save"},
                    {"text": "🗑️ Delete", "callback_data": "job:delete"},
                ],
            ]
        }

        await bot.send_message(
            chat_id=chat_id,
            text=text_msg,
            parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True,
        )
        log.info(f"Sent job to {chat_id}: {title[:40]}")

    except Exception as e:
        log.exception(f"send_job error: {e}")

# =====================================================
# SENT JOB FILTER
# =====================================================
def has_been_sent(s, user_id, job_uid):
    """Check if job already sent to user."""
    r = s.execute(
        text("SELECT 1 FROM sent_job WHERE user_id=:u AND job_uid=:j LIMIT 1"),
        {"u": user_id, "j": job_uid},
    ).fetchone()
    return bool(r)


def mark_as_sent(s, user_id, job_uid):
    """Mark job as sent."""
    s.execute(
        text(
            "INSERT INTO sent_job (user_id, job_uid, sent_at) VALUES (:u, :j, NOW() AT TIME ZONE 'UTC')"
        ),
        {"u": user_id, "j": job_uid},
    )
    s.commit()

# =====================================================
# MAIN LOOP
# =====================================================
async def worker_loop(bot):
    while True:
        try:
            with get_session() as s:
                users = s.execute(
                    text(
                        'SELECT id, telegram_id FROM "user" WHERE is_active=TRUE AND is_blocked=FALSE'
                    )
                ).fetchall()

            for uid, tid in users:
                keywords = list_keywords(uid)
                if not keywords:
                    continue

                log.debug(f"tick user={tid} keywords={keywords}")

                # ----------------- FREELANCER -----------------
                freelancer_jobs = await fetch_freelancer_jobs(keywords)
                log.info(f"Freelancer fetched {len(freelancer_jobs)} items")

                # ----------------- PEOPLEPERHOUR -----------------
                pph_jobs = []
                try:
                    pph_jobs = await fetch_pph_graphql(keywords)
                    if not pph_jobs:
                        # Fallback to HTML
                        log.warning("PPH GraphQL empty — switching to HTML fallback")
                        pph_jobs = await fetch_pph_html(keywords)
                except Exception as e:
                    log.warning(f"PPH GraphQL error: {e}")
                    try:
                        pph_jobs = await fetch_pph_html(keywords)
                    except Exception as e2:
                        log.warning(f"PPH HTML fallback error: {e2}")

                log.info(f"PPH total merged: {len(pph_jobs)}")

                # ----------------- GREEK PLATFORMS -----------------
                gr_jobs = []
                try:
                    gr_jobs += await fetch_skywalker_jobs(keywords)
                    gr_jobs += await fetch_kariera_jobs(keywords)
                except Exception as e:
                    log.warning(f"Greek feeds error: {e}")

                # ----------------- MERGE & FILTER -----------------
                all_jobs = freelancer_jobs + pph_jobs + gr_jobs
                unique = []
                seen = set()

                for j in all_jobs:
                    job_uid = j.get("uid") or j.get("original_url")
                    if not job_uid or job_uid in seen:
                        continue
                    seen.add(job_uid)
                    if has_been_sent(s, uid, job_uid):
                        continue
                    unique.append(j)

                # ----------------- SEND -----------------
                for job in unique:
                    await send_job(bot, tid, job)
                    mark_as_sent(s, uid, job.get("uid") or job.get("original_url"))
                    await asyncio.sleep(2.5)

                log.info(f"User {tid}: sent {len(unique)} new jobs")
                await asyncio.sleep(1.5)

            record_event("peopleperhour")
            record_event("freelancer")
            record_event("skywalker")
            record_event("kariera")

        except Exception as e:
            log.exception(f"[runner compat] pipeline error: {e}")

        await asyncio.sleep(WORKER_INTERVAL or 120)

# =====================================================
# ENTRY POINT
# =====================================================
if __name__ == "__main__":
    import telegram
    BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not BOT_TOKEN:
        raise RuntimeError("Missing BOT_TOKEN in environment")
    bot = telegram.Bot(token=BOT_TOKEN)
    asyncio.run(worker_loop(bot))
