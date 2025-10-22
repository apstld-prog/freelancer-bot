import os
import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy import text
from db import get_session
from db_events import record_event
from db_keywords import list_keywords
from config import WORKER_INTERVAL
from platform_freelancer import get_items as fetch_freelancer_jobs
from platform_peopleperhour import get_items as fetch_pph_jobs
from platform_skywalker import fetch_skywalker_jobs
from platform_kariera import fetch_kariera_jobs
import telegram

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker")

# =====================================================
# ENV CONFIG
# =====================================================
FREELANCER_INTERVAL = int(os.getenv("FREELANCER_INTERVAL", "60"))
PPH_INTERVAL = int(os.getenv("PPH_INTERVAL", "300"))
GREEK_INTERVAL = int(os.getenv("GREEK_INTERVAL", "300"))

PPH_FAIL_LIMIT = 3
PPH_COOLDOWN = 1800  # 30 min pause if 3x fails

# =====================================================
# UTILITIES
# =====================================================
async def send_job(bot, chat_id, job):
    try:
        title = job.get("title", "").strip()
        desc = (job.get("description") or "").strip()
        mk = job.get("matched_keyword", "")
        url = job.get("original_url", "")
        src = job.get("source", "Unknown")

        bmin, bmax = job.get("budget_min"), job.get("budget_max")
        cur = job.get("budget_currency") or "USD"
        if bmin and bmax and bmin != bmax:
            budget = f"{bmin}–{bmax} {cur}"
        elif bmin:
            budget = f"{bmin} {cur}"
        else:
            budget = "N/A"

        txt = f"<b>{title}</b>\n<b>Budget:</b> {budget}\n<b>Source:</b> {src}\n"
        if mk:
            txt += f"<b>Match:</b> {mk}\n\n"
        txt += desc

        kb = {
            "inline_keyboard": [
                [{"text": "📄 Proposal", "url": url}],
                [
                    {"text": "⭐ Save", "callback_data": "job:save"},
                    {"text": "🗑️ Delete", "callback_data": "job:delete"},
                ],
            ]
        }

        await bot.send_message(
            chat_id=chat_id,
            text=txt,
            parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True,
        )
        log.info(f"Sent to {chat_id}: {title[:40]}")
    except Exception as e:
        log.warning(f"send_job error: {e}")

def has_been_sent(s, uid, job_uid):
    r = s.execute(
        text("SELECT 1 FROM sent_job WHERE user_id=:u AND job_uid=:j LIMIT 1"),
        {"u": uid, "j": job_uid},
    ).fetchone()
    return bool(r)

def mark_as_sent(s, uid, job_uid):
    s.execute(
        text(
            "INSERT INTO sent_job (user_id, job_uid, sent_at) VALUES (:u, :j, NOW() AT TIME ZONE 'UTC')"
        ),
        {"u": uid, "j": job_uid},
    )
    s.commit()

# =====================================================
# MAIN LOOP
# =====================================================
async def worker_loop(bot):
    pph_fail_count = 0
    pph_paused_until = None

    while True:
        start = datetime.now(timezone.utc)
        try:
            with get_session() as s:
                users = s.execute(
                    text(
                        'SELECT id, telegram_id FROM "user" WHERE is_active=TRUE AND is_blocked=FALSE'
                    )
                ).fetchall()

            for uid, tid in users:
                kws = list_keywords(uid)
                if not kws:
                    continue

                log.info(f"User {tid}: {kws}")

                freelancer_jobs, pph_jobs, gr_jobs = [], [], []

                # FREELANCER (every FREELANCER_INTERVAL)
                if (start.minute % (FREELANCER_INTERVAL or 1)) == 0:
                    try:
                        freelancer_jobs = fetch_freelancer_jobs(kws)
                        log.info(f"Freelancer: {len(freelancer_jobs)} jobs")
                    except Exception as e:
                        log.warning(f"Freelancer err: {e}")

                # PPH (every PPH_INTERVAL)
                now = datetime.now().timestamp()
                if (
                    pph_paused_until is None or now > pph_paused_until
                ) and (start.minute % (PPH_INTERVAL // 60 or 1)) == 0:
                    try:
                        pph_jobs = fetch_pph_jobs(kws)
                        log.info(f"PPH: {len(pph_jobs)} jobs")

                        if len(pph_jobs) == 0:
                            pph_fail_count += 1
                            log.warning(f"PPH empty (#{pph_fail_count})")
                            if pph_fail_count >= PPH_FAIL_LIMIT:
                                pph_paused_until = now + PPH_COOLDOWN
                                pph_fail_count = 0
                                log.warning("PPH temporarily paused 30m")
                        else:
                            pph_fail_count = 0
                    except Exception as e:
                        log.warning(f"PPH fetch err: {e}")

                # GREEK FEEDS (every GREEK_INTERVAL)
                if (start.minute % (GREEK_INTERVAL // 60 or 1)) == 0:
                    try:
                        gr_jobs += await fetch_skywalker_jobs(kws)
                        gr_jobs += await fetch_kariera_jobs(kws)
                        log.info(f"Greek feeds: {len(gr_jobs)} jobs")
                    except Exception as e:
                        log.warning(f"Greek feeds err: {e}")

                # MERGE + DEDUP
                all_jobs = freelancer_jobs + pph_jobs + gr_jobs
                seen = set()
                new_jobs = []
                with get_session() as s:
                    for j in all_jobs:
                        jid = j.get("uid") or j.get("original_url")
                        if not jid or jid in seen:
                            continue
                        seen.add(jid)
                        if has_been_sent(s, uid, jid):
                            continue
                        new_jobs.append(j)
                        mark_as_sent(s, uid, jid)

                # SEND
                for j in new_jobs:
                    await send_job(bot, tid, j)
                    await asyncio.sleep(2.5)

                log.info(f"User {tid}: sent {len(new_jobs)} new")

            # record events
            record_event("freelancer")
            record_event("peopleperhour")
            record_event("skywalker")
            record_event("kariera")

        except Exception as e:
            log.exception(f"worker error: {e}")

        await asyncio.sleep(WORKER_INTERVAL)

# =====================================================
# ENTRY POINT
# =====================================================
if __name__ == "__main__":
    token = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Missing BOT_TOKEN")
    bot = telegram.Bot(token=token)
    asyncio.run(worker_loop(bot))
