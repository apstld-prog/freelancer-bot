import asyncio
import logging
import os
import hashlib
from datetime import datetime, timedelta

import psycopg2
import psycopg2.extras

from platform_freelancer import fetch_freelancer_jobs
from platform_peopleperhour import fetch_pph_jobs
from platform_skywalker import fetch_skywalker_jobs
from currency_usd import usd_line

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker")

DATABASE_URL = (os.getenv("DATABASE_URL") or "").replace("postgresql+psycopg2://", "postgresql://")
FRESH_HOURS = int(os.getenv("FRESH_HOURS", "48"))
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "180"))

# ---------------- DB ----------------
def db_connect():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL env var is required")
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def ensure_sent_table():
    """
    Δημιουργεί/διορθώνει τον πίνακα sent_job ώστε να υπάρχουν ΠΑΝΤΑ:
      - user_id BIGINT
      - job_hash TEXT
      - sent_at TIMESTAMPTZ (UTC default)
    και το index (user_id, job_hash).
    """
    conn = db_connect()
    cur = conn.cursor()
    # 1) Δημιουργία αν δεν υπάρχει
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sent_job (
            user_id BIGINT,
            job_hash TEXT,
            sent_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC')
        )
    """)
    # 2) Ασφαλή ALTERs για παλιά σχήματα
    cur.execute("ALTER TABLE sent_job ADD COLUMN IF NOT EXISTS user_id BIGINT")
    cur.execute("ALTER TABLE sent_job ADD COLUMN IF NOT EXISTS job_hash TEXT")
    cur.execute("ALTER TABLE sent_job ADD COLUMN IF NOT EXISTS sent_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC')")
    # 3) Index αφού σιγουρευτούμε ότι υπάρχουν οι στήλες
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM   pg_class c
                JOIN   pg_namespace n ON n.oid = c.relnamespace
                WHERE  c.relname = 'idx_sent_job_user_hash'
                AND    n.nspname = 'public'
            ) THEN
                EXECUTE 'CREATE INDEX idx_sent_job_user_hash ON sent_job(user_id, job_hash)';
            END IF;
        END$$;
    """)
    conn.commit()
    cur.close()
    conn.close()

def has_been_sent(tid: int, job_hash: str) -> bool:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sent_job WHERE user_id=%s AND job_hash=%s LIMIT 1", (tid, job_hash))
    ok = cur.fetchone() is not None
    cur.close()
    conn.close()
    return ok

def mark_as_sent(tid: int, job_hash: str) -> None:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("INSERT INTO sent_job (user_id, job_hash) VALUES (%s,%s)", (tid, job_hash))
    conn.commit()
    cur.close()
    conn.close()

def get_users_with_keywords():
    """
    Διαβάζει:
      - user.id (DB id), user.telegram_id, countries, is_active, is_blocked
      - keywords από table `keyword` (όπως στο δικό σου schema)
    Επιστρέφει λίστα από dicts.
    """
    conn = db_connect()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        'SELECT id, telegram_id, COALESCE(countries, \'ALL\') AS countries, is_active, is_blocked '
        'FROM "user" WHERE is_active=TRUE'
    )
    users = cur.fetchall() or []
    for u in users:
        db_user_id = u["id"]
        cur.execute('SELECT keyword FROM keyword WHERE user_id=%s ORDER BY id ASC', (db_user_id,))
        rows = cur.fetchall() or []
        kws = [(r["keyword"] or "").strip() for r in rows if (r.get("keyword") or "").strip()]
        u["keywords_list"] = kws
        u["keywords_str"] = ", ".join(kws)
    cur.close()
    conn.close()
    return users

# ------------- Filtering -------------
def is_fresh(job: dict) -> bool:
    ts = job.get("time_submitted")
    if not ts:
        return True
    try:
        job_time = datetime.fromtimestamp(ts)
    except Exception:
        return True
    return (datetime.utcnow() - job_time) < timedelta(hours=FRESH_HOURS)

def matches_keywords(job: dict, kw_list) -> bool:
    if not kw_list:
        return False
    title = (job.get("title") or "").lower()
    desc  = (job.get("description") or "").lower()
    blob = f"{title} {desc}"
    for kw in kw_list:
        k = kw.lower().strip()
        if not k:
            continue
        if k in blob:
            job["matched_keyword"] = k
            return True
    return False

def matches_country(job: dict, countries: str) -> bool:
    # countries: "ALL" ή "US,UK"
    if not countries or countries.upper() == "ALL":
        return True
    val = (job.get("country") or job.get("location") or "").upper()
    if not val:
        # Αν η αγγελία δεν δίνει χώρα, επιτρέπεται (χαλαρό φίλτρο)
        return True
    wanted = [c.strip().upper() for c in countries.split(",") if c.strip()]
    return any(c in val for c in wanted)

# ------------- Send -------------
async def send_job(bot, chat_id: int, job: dict):
    try:
        title = job.get("title") or "Untitled"
        src   = job.get("source") or ""
        match_kw = job.get("matched_keyword") or ""
        cur_code = job.get("budget_currency") or ""
        bmin = job.get("budget_min") or 0
        bmax = job.get("budget_max") or 0
        usd_text = usd_line(bmin, bmax, cur_code) or ""

        text = f"<b>{title}</b>\n"
        if bmin or bmax:
            text += f"<b>Budget:</b> {bmin}–{bmax} {cur_code} {usd_text}\n"
        else:
            text += f"<b>Budget:</b> N/A\n"
        text += f"<b>Source:</b> {src}\n"
        if match_kw:
            text += f"<b>Match:</b> {match_kw}\n"
        desc = (job.get("description") or "").strip()
        if desc:
            text += f"{desc[:400]}\n"

        rel = job.get("relative_time") or ""
        if rel:
            text += f"{rel}\n"

        kb = [
            [
                {"text": "📄 Proposal", "url": job.get("affiliate_url") or job.get("original_url")},
                {"text": "🔗 Original", "url": job.get("original_url")},
            ],
            [
                {"text": "⭐ Save", "callback_data": "job:save"},
                {"text": "🗑️ Delete", "callback_data": "job:delete"},
            ],
        ]

        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup={"inline_keyboard": kb},
            disable_web_page_preview=True,
        )
        log.info("Sent job → %s: %s", chat_id, title[:60])
    except Exception as e:
        log.warning("send_job error: %s", e)

# ------------- Main per-user -------------
async def process_user(bot, user_row: dict):
    if user_row.get("is_blocked"):
        return
    chat_id = int(user_row["telegram_id"])
    countries = (user_row.get("countries") or "ALL").upper()
    kw_list = user_row.get("keywords_list") or []

    log.info("[Worker] Fetching for user %s (kw=%s, countries=%s)",
             chat_id,
             (", ".join(kw_list) if kw_list else ""),
             countries)

    all_jobs = []
    try:
        all_jobs.extend(fetch_freelancer_jobs(kw_list))
        all_jobs.extend(fetch_pph_jobs(kw_list))
        all_jobs.extend(fetch_skywalker_jobs(kw_list))
    except Exception as e:
        log.exception("Fetch error: %s", e)

    sent = 0
    for job in all_jobs:
        if not is_fresh(job):
            continue
        if not matches_keywords(job, kw_list):
            continue
        if not matches_country(job, countries):
            continue

        jhash = hashlib.sha1((job.get("title","") + job.get("original_url","")).encode("utf-8","ignore")).hexdigest()
        if has_been_sent(chat_id, jhash):
            continue
        mark_as_sent(chat_id, jhash)

        await send_job(bot, chat_id, job)
        sent += 1
        await asyncio.sleep(1.2)

    log.info("✅ Sent %d jobs → %s", sent, chat_id)

# ------------- Loop -------------
async def main_loop(bot):
    ensure_sent_table()
    while True:
        try:
            users = get_users_with_keywords()
            log.info("[Worker] Total users: %d", len(users))
            for u in users:
                await process_user(bot, u)
                await asyncio.sleep(2.5)
            log.info("[Worker] Cycle complete. Sleeping...")
        except Exception as e:
            log.exception("main_loop error: %s", e)
        await asyncio.sleep(WORKER_INTERVAL)

# ------------- Entry -------------
if __name__ == "__main__":
    from telegram import Bot
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN/BOT_TOKEN env var is required")
    bot = Bot(token)
    asyncio.run(main_loop(bot))
