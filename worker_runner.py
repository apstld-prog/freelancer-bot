#!/usr/bin/env python3
# worker_runner.py — FINAL STABLE EDITION
import os
import asyncio
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set

from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from sqlalchemy import text as _sql_text
from db import get_session as _get_session
from db_keywords import list_keywords as _list_keywords

import worker as _worker

# ---------------- Logging ----------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
log = logging.getLogger("worker")

# ---------------- Intervals ----------------
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "180"))
FREELANCER_INTERVAL = int(os.getenv("FREELANCER_INTERVAL", "60"))
PPH_INTERVAL = int(os.getenv("PPH_INTERVAL", "300"))
GREEK_INTERVAL = int(os.getenv("GREEK_INTERVAL", "300"))

FRESH_HOURS = int(os.getenv("FRESH_WINDOW_HOURS", "48"))

# ---------------- DB Helpers ----------------
def _ensure_sent_schema():
    with _get_session() as s:
        s.execute(_sql_text("""
            CREATE TABLE IF NOT EXISTS sent_job (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                job_key TEXT NOT NULL,
                sent_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC'),
                UNIQUE (user_id, job_key)
            )
        """))
        s.commit()

def _already_sent(user_id: int, job_key: str) -> bool:
    _ensure_sent_schema()
    with _get_session() as s:
        row = s.execute(_sql_text(
            "SELECT 1 FROM sent_job WHERE user_id=:u AND job_key=:k LIMIT 1"
        ), {"u": user_id, "k": job_key}).fetchone()
        return row is not None

def _mark_sent(user_id: int, job_key: str) -> None:
    with _get_session() as s:
        s.execute(_sql_text(
            "INSERT INTO sent_job (user_id, job_key) VALUES (:u, :k) ON CONFLICT DO NOTHING"
        ), {"u": user_id, "k": job_key})
        s.commit()

def _fetch_all_users() -> List[int]:
    ids: Set[int] = set()
    with _get_session() as s:
        rows = s.execute(_sql_text(
            'SELECT DISTINCT telegram_id FROM "user" WHERE telegram_id IS NOT NULL AND COALESCE(is_blocked,false)=false AND COALESCE(is_active,true)=true'
        )).fetchall()
        ids.update(int(r[0]) for r in rows if r[0] is not None)
    return sorted(list(ids))

def _fetch_user_keywords(telegram_id: int) -> List[str]:
    try:
        with _get_session() as s:
            row = s.execute(_sql_text('SELECT id FROM "user" WHERE telegram_id=:tid'), {"tid": telegram_id}).fetchone()
            if not row:
                return []
            uid = int(row[0])
        kws = _list_keywords(uid) or []
        return [k.strip() for k in kws if k and k.strip()]
    except Exception:
        return []

# ---------------- Utils ----------------
def _job_key(it: Dict) -> str:
    base = (it.get("url") or it.get("original_url") or "").strip()
    if not base:
        base = f"{it.get('source','')}::{(it.get('title') or '')[:160]}"
    return hashlib.sha1(base.encode("utf-8", "ignore")).hexdigest()

def _time_ago(dt: datetime) -> str:
    now = datetime.now(timezone.utc)
    delta = now - dt
    s = int(delta.total_seconds())
    if s < 60:
        return "just now"
    m = s // 60
    if m < 60:
        return f"{m} minute{'s' if m != 1 else ''} ago"
    h = m // 60
    if h < 24:
        return f"{h} hour{'s' if h != 1 else ''} ago"
    d = h // 24
    return f"{d} day{'s' if d != 1 else ''} ago"

def _extract_dt(it: Dict) -> Optional[datetime]:
    for k in ("time_submitted", "created_at", "posted_at", "timestamp", "pub_date"):
        v = it.get(k)
        if not v:
            continue
        try:
            dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc)
        except Exception:
            continue
    return None

# ---------------- Message & UI ----------------
def _compose_message(it: Dict) -> str:
    title = (it.get("title") or "Untitled").strip()
    desc = (it.get("description") or "").strip()
    if len(desc) > 700:
        desc = desc[:700] + "…"
    src = (it.get("source") or "Freelancer").strip()
    dt = _extract_dt(it)
    budget = ""
    if it.get("budget_min") or it.get("budget_max"):
        currency = it.get("budget_currency") or "USD"
        budget = f"{it.get('budget_min','')}–{it.get('budget_max','')} {currency}"

    lines = [f"<b>{title}</b>"]
    if budget:
        lines.append(f"<b>Budget:</b> {budget}")
    lines.append(f"<b>Source:</b> {src}")
    if dt:
        lines.append(f"<b>Posted:</b> {_time_ago(dt)}")
    mk = it.get("matched_keyword")
    if mk:
        lines.append(f"<b>Match:</b> {mk}")
    lines.append(desc)
    return "\n".join(lines)

def _build_keyboard(links: Dict[str, Optional[str]]):
    row1 = [
        InlineKeyboardButton("📄 Proposal", url=(links.get("proposal") or links.get("original") or "")),
        InlineKeyboardButton("🔗 Original", url=(links.get("original") or "")),
    ]
    row2 = [
        InlineKeyboardButton("⭐ Save", callback_data="job:save"),
        InlineKeyboardButton("🗑️ Delete", callback_data="job:delete"),
    ]
    return InlineKeyboardMarkup([row1, row2])

# ---------------- Core ----------------
async def _send_items(bot: Bot, chat_id: int, items: List[Dict], per_user_batch: int):
    sent = 0
    for it in items:
        if sent >= per_user_batch:
            break
        key = _job_key(it)
        if _already_sent(chat_id, key):
            continue
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=_compose_message(it),
                parse_mode=ParseMode.HTML,
                reply_markup=_build_keyboard(it),
                disable_web_page_preview=True,
            )
            _mark_sent(chat_id, key)
            sent += 1
            await asyncio.sleep(0.35)
        except Exception as e:
            log.warning(f"send_message failed for {chat_id}: {e}")

async def amain():
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN env var required")

    bot = Bot(token=token)
    per_user_batch = int(os.getenv("BATCH_PER_TICK", "5"))
    last_run = {"freelancer": 0, "pph": 0, "skywalker": 0}

    while True:
        users = _fetch_all_users()
        now = datetime.now(timezone.utc).timestamp()

        for tid in users:
            kws = _fetch_user_keywords(tid)
            if not kws:
                continue

            # Freelancer
            if now - last_run["freelancer"] >= FREELANCER_INTERVAL:
                try:
                    jobs = _worker.run_pipeline(kws)
                    if jobs:
                        await _send_items(bot, tid, jobs, per_user_batch)
                        log.info(f"[Freelancer] sent {len(jobs)} jobs → {tid}")
                    last_run["freelancer"] = now
                except Exception as e:
                    log.warning(f"Freelancer error: {e}")

            # PPH
            if now - last_run["pph"] >= PPH_INTERVAL:
                try:
                    import platform_peopleperhour as pph
                    jobs = pph.get_items(kws)
                    if jobs:
                        await _send_items(bot, tid, jobs, per_user_batch)
                        log.info(f"[PPH] sent {len(jobs)} jobs → {tid}")
                    last_run["pph"] = now
                except Exception as e:
                    log.warning(f"PPH error: {e}")

            # Skywalker
            if now - last_run["skywalker"] >= GREEK_INTERVAL:
                try:
                    import platform_skywalker as sky
                    jobs = sky.fetch_skywalker_jobs(kws)
                    if jobs:
                        await _send_items(bot, tid, jobs, per_user_batch)
                        log.info(f"[Skywalker] sent {len(jobs)} jobs → {tid}")
                    last_run["skywalker"] = now
                except Exception as e:
                    log.warning(f"Skywalker error: {e}")

        await asyncio.sleep(WORKER_INTERVAL)

if __name__ == "__main__":
    log.info("🚀 Starting unified worker (Freelancer + PPH + Greek feeds)")
    asyncio.run(amain())
