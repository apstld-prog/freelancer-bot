import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, List
import httpx

# ✅ FIXED IMPORT (db_events API)
from db_events import ensure_feed_events_schema as ensure_schema, record_event as log_platform_event

from db import get_session
from job_logic import match_keywords, make_key
from sqlalchemy import text as sqltext

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker")

# --- Flexible imports for platform fetchers ---
try:
    from platform_freelancer import fetch_freelancer_jobs as _fetch_freelancer
except Exception:
    try:
        from platform_freelancer import fetch_jobs as _fetch_freelancer
    except Exception:
        from platform_freelancer import fetch as _fetch_freelancer

try:
    from platform_skywalker import fetch_skywalker_jobs as _fetch_skywalker
except Exception:
    try:
        from platform_skywalker import fetch_jobs as _fetch_skywalker
    except Exception:
        from platform_skywalker import fetch as _fetch_skywalker


# 🔹 Inline replacement for send_job_to_user (no external telegram_bot module)
def send_job_to_user(chat_id: int, item: Dict) -> None:
    """Sends a job message to the user via Telegram Bot API."""
    BOT_TOKEN = (
        os.getenv("TELEGRAM_BOT_TOKEN")
        or os.getenv("BOT_TOKEN")
        or os.getenv("TELEGRAM_TOKEN")
    )
    if not BOT_TOKEN:
        log.warning("No BOT_TOKEN in environment.")
        return

    TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    title = item.get("title", "Untitled")

    # Format budget
    bmin = item.get("budget_min_usd") or item.get("budget_min")
    bmax = item.get("budget_max_usd") or item.get("budget_max")
    cur = "USD" if (item.get("budget_min_usd") or item.get("budget_max_usd")) else (item.get("currency") or "")
    if bmin and bmax:
        budget_str = f"{bmin}–{bmax} {cur}".strip()
    elif bmin:
        budget_str = f"{bmin} {cur}".strip()
    elif bmax:
        budget_str = f"{bmax} {cur}".strip()
    else:
        budget_str = "N/A"

    orig = item.get("original_url") or item.get("url") or ""
    aff = item.get("affiliate_url") or orig

    text_msg = (
        f"💼 <b>{title}</b>\n"
        f"💰 <b>Budget:</b> {budget_str}\n"
        f"📦 <b>Source:</b> {item.get('source', 'unknown').title()}\n"
    )

    kb = {
        "inline_keyboard": [
            [{"text": "📄 Proposal", "url": aff or orig},
             {"text": "🔗 Original", "url": orig or aff}],
            [{"text": "⭐ Save", "callback_data": "job:save"},
             {"text": "🗑️ Delete", "callback_data": "job:delete"}]
        ]
    }

    try:
        httpx.post(
            TG_API,
            json={
                "chat_id": chat_id,
                "text": text_msg,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "reply_markup": kb,
            },
            timeout=20,
        )
    except Exception as e:
        log.warning(f"[send] to {chat_id} failed: {e}")


# --------------- MAIN WORKER LOGIC ---------------- #

async def maybe_await(result):
    if asyncio.iscoroutine(result):
        return await result
    return result


def ensure_sent_table():
    with get_session() as s:
        s.execute(
            """
            CREATE TABLE IF NOT EXISTS sent_job (
                job_key TEXT PRIMARY KEY,
                sent_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC')
            );
            """
        )
        s.commit()


def prune_sent_table(days: int = 7) -> None:
    with get_session() as s:
        s.execute(
            sqltext(
                "DELETE FROM sent_job WHERE sent_at < (NOW() AT TIME ZONE 'UTC') - INTERVAL :d || ' days'"
            ).bindparams(d=days)
        )
        s.commit()


def deliver_to_users(items: List[Dict]):
    if not items:
        return
    ensure_sent_table()
    with get_session() as s:
        rows = s.execute(
            'SELECT id, telegram_id FROM "user" WHERE is_blocked=FALSE'
        ).fetchall()
        users = [(int(r[0]), int(r[1])) for r in rows]
        log.info("[deliver] users loaded: %d", len(users))

    for item in items:
        key = make_key(item)
        with get_session() as s:
            res = s.execute(
                sqltext(
                    "INSERT INTO sent_job(job_key) VALUES (:k) ON CONFLICT DO NOTHING RETURNING job_key"
                ),
                {"k": key},
            ).fetchone()
            s.commit()
        if not res:
            continue  # already sent before

        for uid, tid in users:
            try:
                send_job_to_user(tid, item)
                time.sleep(0.5)
            except Exception as e:
                log.warning(f"[deliver] send fail user={tid} err={e}")


async def run_pipeline(keywords: List[str]):
    all_items: List[Dict] = []

    # Freelancer
    try:
        fl_items = await maybe_await(_fetch_freelancer(keywords))
        all_items.extend(fl_items or [])
    except Exception as e:
        log.error(f"[freelancer] fetch error: {e}")

    # Skywalker
    try:
        sk_items = await maybe_await(_fetch_skywalker(keywords))
        all_items.extend(sk_items or [])
    except Exception as e:
        log.error(f"[skywalker] fetch error: {e}")

    # Filter by keywords
    filtered = [i for i in all_items if match_keywords(i, keywords)]
    log.info(f"[Worker] cycle completed — keywords={len(keywords)}, items={len(filtered)}")
    deliver_to_users(filtered)


def get_keywords() -> List[str]:
    with get_session() as s:
        rows = s.execute("SELECT DISTINCT value FROM keyword").fetchall()
        return [r[0] for r in rows]


if __name__ == "__main__":
    log.info("[Worker] ✅ Running (interval=%ss)", os.getenv("WORKER_INTERVAL", "120"))
    ensure_schema()
    ensure_sent_table()
    interval = int(os.getenv("WORKER_INTERVAL", "120"))
    while True:
        try:
            prune_sent_table(days=7)
            kw = get_keywords()
            asyncio.run(run_pipeline(kw))
        except Exception as e:
            log.error(f"[Worker] error: {e}")
        time.sleep(interval)
