import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, List

import httpx

# ✅ FIXED IMPORT
from db_events import ensure_feed_events_schema as ensure_schema, record_event as log_platform_event

from db import get_session
from platform_freelancer import fetch_freelancer_jobs
from platform_skywalker import fetch_skywalker_jobs
from job_logic import match_keywords, make_key
from sqlalchemy import text as sqltext
from telegram_bot import send_job_to_user

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker")


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
        try:
            log.info("[deliver] users loaded: %d", len(users))
        except Exception:
            pass

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
    all_items = []
    try:
        fl_items = await fetch_freelancer_jobs(keywords)
        all_items.extend(fl_items)
    except Exception as e:
        log.error(f"[freelancer] fetch error: {e}")

    try:
        sk_items = await fetch_skywalker_jobs(keywords)
        all_items.extend(sk_items)
    except Exception as e:
        log.error(f"[skywalker] fetch error: {e}")

    filtered = [i for i in all_items if match_keywords(i, keywords)]
    log.info(f"[Worker] cycle completed — keywords={len(keywords)}, items={len(filtered)}")
    deliver_to_users(filtered)


def get_keywords() -> List[str]:
    with get_session() as s:
        rows = s.execute("SELECT keyword FROM keyword").fetchall()
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
