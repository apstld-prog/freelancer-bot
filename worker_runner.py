# worker_runner.py — FINAL VERSION (Oct 2025)
# ✅ Includes:
#  - freelancer + skywalker + peopleperhour fetch
#  - humanized posted_ago
#  - currency detection
#  - per-user deduplication via DB (sent_job)
#  - safe pacing & error handling

import asyncio, logging, time
from datetime import datetime, timezone
from sqlalchemy import text

from db import get_session
from db_keywords import list_keywords
from worker import run_pipeline
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder
from config import TELEGRAM_BOT_TOKEN, WORKER_INTERVAL

log = logging.getLogger("worker")
logging.basicConfig(level=logging.INFO)

# ---------- ensure table for sent dedup ----------
def ensure_sent_schema():
    with get_session() as s:
        s.execute(text("""
            CREATE TABLE IF NOT EXISTS sent_job (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                job_key TEXT NOT NULL,
                sent_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC')
            );
        """))
        s.execute(text("CREATE INDEX IF NOT EXISTS idx_sent_job_user_job ON sent_job(user_id, job_key);"))
        s.commit()
    log.info("✅ ensured sent_job schema")

ensure_sent_schema()

# ---------- helpers ----------
def make_job_card(job):
    """Prepare Telegram message text and keyboard identical to Freelancer format."""
    title = job.get("title", "(no title)")
    desc = (job.get("description") or "").strip()
    kw = job.get("matched_keyword", "")
    src = job.get("source", "Unknown")
    ago = job.get("posted_ago") or ""

    bmin, bmax = job.get("budget_min"), job.get("budget_max")
    cur = job.get("budget_currency") or "USD"
    usd_min, usd_max = job.get("budget_min_usd"), job.get("budget_max_usd")
    budget_line = ""
    if bmin and bmax:
        if usd_min and usd_max and cur != "USD":
            budget_line = f"<b>Budget:</b> {bmin}–{bmax} {cur} (~${usd_min:.0f}–${usd_max:.0f} USD)"
        else:
            budget_line = f"<b>Budget:</b> {bmin}–{bmax} {cur}"
    elif bmin:
        budget_line = f"<b>Budget:</b> {bmin} {cur}"

    lines = [f"<b>{title}</b>"]
    if budget_line:
        lines.append(budget_line)
    if ago:
        lines.append(f"<b>Posted:</b> {ago}")
    lines.append(f"<b>Source:</b> {src}")
    if kw:
        lines.append(f"<b>Match:</b> {kw}")
    if desc:
        lines.append(desc)

    msg = "\n".join(lines)

    url = job.get("original_url") or job.get("affiliate_url") or ""
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Proposal", url=url),
         InlineKeyboardButton("🔗 Original", url=url)],
        [InlineKeyboardButton("⭐ Save", callback_data="job:save"),
         InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")],
    ])
    return msg, kb

async def send_job_to_user(bot, user_id, job):
    """Send job if not sent before."""
    job_key = str(job.get("id") or job.get("original_url") or job.get("title") or "")[:512]

    # skip if already sent
    with get_session() as s:
        exists = s.execute(
            text("SELECT 1 FROM sent_job WHERE user_id=:u AND job_key=:j LIMIT 1"),
            {"u": user_id, "j": job_key}
        ).scalar()
    if exists:
        return False  # already sent

    msg, kb = make_job_card(job)
    try:
        await bot.send_message(chat_id=user_id, text=msg,
                               parse_mode=ParseMode.HTML,
                               disable_web_page_preview=True,
                               reply_markup=kb)
        # mark as sent
        with get_session() as s:
            s.execute(text("INSERT INTO sent_job (user_id, job_key) VALUES (:u, :j)"),
                      {"u": user_id, "j": job_key})
            s.commit()
        return True
    except Exception as e:
        log.warning("send_job_to_user failed for %s: %s", user_id, e)
        return False

# ---------- main loop ----------
async def worker_loop(app):
    bot = app.bot
    while True:
        try:
            with get_session() as s:
                users = s.execute(text('SELECT id, telegram_id FROM "user" WHERE is_active=TRUE AND is_blocked=FALSE')).fetchall()

            for uid, tid in users:
                try:
                    kws = list_keywords(uid)
                    if not kws:
                        continue
                    jobs = run_pipeline(kws)
                    sent_count = 0
                    for job in jobs:
                        ok = await send_job_to_user(bot, tid, job)
                        if ok:
                            sent_count += 1
                    log.debug(f"tick user={tid} filtered={len(jobs)} sent={sent_count}")
                    await asyncio.sleep(1.5)
                except Exception as ue:
                    log.warning("user-loop error for %s: %s", tid, ue)
                    continue
        except Exception as e:
            log.warning("[runner compat] pipeline error: %s", e)
        await asyncio.sleep(WORKER_INTERVAL)

# ---------- bootstrap ----------
async def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    await worker_loop(app)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("stopped manually")
