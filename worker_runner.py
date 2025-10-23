#!/usr/bin/env python3
# worker_runner.py — unified runner (Freelancer + PPH + Greek feeds)
import os, logging, asyncio, hashlib
from typing import Dict, List, Optional, Set
from html import escape as _esc
from datetime import datetime, timezone, timedelta

import worker as _worker
from sqlalchemy import text as _sql_text
from db import get_session as _get_session
from db_keywords import list_keywords as _list_keywords
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode

# ---------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
log = logging.getLogger("worker")

FRESH_HOURS = int(os.getenv("FRESH_WINDOW_HOURS", "48"))
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "180"))
_last_sent_at: Dict[str, float] = {}

# ---------------------------------------------------
def _now_utc(): return datetime.now(timezone.utc)
def _h(s: str): return _esc((s or '').strip(), quote=False)

def _ensure_sent_schema():
    with _get_session() as s:
        s.execute(_sql_text("""
            CREATE TABLE IF NOT EXISTS sent_job (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                job_key TEXT NOT NULL,
                sent_at TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'UTC'),
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

def _mark_sent(user_id: int, job_key: str):
    with _get_session() as s:
        s.execute(_sql_text(
            "INSERT INTO sent_job (user_id, job_key) VALUES (:u, :k) ON CONFLICT DO NOTHING"
        ), {"u": user_id, "k": job_key})
        s.commit()

def _fetch_all_users() -> List[int]:
    with _get_session() as s:
        rows = s.execute(_sql_text(
            'SELECT DISTINCT telegram_id FROM "user" WHERE telegram_id IS NOT NULL AND COALESCE(is_blocked,false)=false AND COALESCE(is_active,true)=true'
        )).fetchall()
    return [int(r[0]) for r in rows if r[0]]

def _fetch_user_keywords(tid: int) -> List[str]:
    try:
        with _get_session() as s:
            row = s.execute(_sql_text('SELECT id FROM "user" WHERE telegram_id=:tid'), {"tid": tid}).fetchone()
            if not row: return []
            uid = int(row[0])
        kws = _list_keywords(uid) or []
        return [k.strip() for k in kws if k.strip()]
    except Exception:
        return []

def _extract_dt(it: Dict) -> Optional[datetime]:
    for k in ("time_submitted","posted_at","created_at","timestamp","date","pub_date","published"):
        v = it.get(k)
        if not v: continue
        try:
            return datetime.fromisoformat(str(v).replace("Z","+00:00")).astimezone(timezone.utc)
        except Exception:
            continue
    return None

def _time_ago(dt: datetime) -> str:
    delta = _now_utc() - dt
    s = int(delta.total_seconds())
    if s < 60: return "just now"
    m = s // 60
    if m < 60: return f"{m} min ago"
    h = m // 60
    if h < 24: return f"{h} h ago"
    d = h // 24
    return f"{d} d ago"

def _compose_message(it: Dict) -> str:
    title = it.get("title") or "Untitled"
    desc = (it.get("description") or "").strip()
    src = (it.get("source") or "Freelancer").strip()
    mk = it.get("matched_keyword") or ""
    budget = it.get("budget") or it.get("budget_amount") or ""
    currency = it.get("currency") or it.get("budget_currency") or ""
    lines = [f"<b>{_h(title)}</b>"]
    if budget:
        lines.append(f"<b>Budget:</b> {_h(str(budget))} {currency}")
    lines.append(f"<b>Source:</b> {_h(src)}")
    if mk:
        lines.append(f"<b>Match:</b> {_h(mk)}")
    dt = _extract_dt(it)
    if dt: lines.append(f"<i>{_time_ago(dt)}</i>")
    if desc: lines.append(_h(desc))
    return "\n".join(lines)

def _build_keyboard(links: Dict[str, Optional[str]]):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Proposal", url=links.get("proposal") or links.get("original") or ""),
         InlineKeyboardButton("🔗 Original", url=links.get("original") or "")],
        [InlineKeyboardButton("⭐ Save", callback_data="job:save"),
         InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")]
    ])

def _resolve_links(it: Dict) -> Dict[str, Optional[str]]:
    u = it.get("original_url") or it.get("url") or ""
    return {"original": u, "proposal": u, "affiliate": it.get("affiliate_url")}

def _job_key(it: Dict) -> str:
    base = (it.get("url") or it.get("original_url") or "").strip()
    if not base: base = f"{it.get('source','')}::{it.get('title','')}"
    return hashlib.sha1(base.encode("utf-8","ignore")).hexdigest()

# ---------------------------------------------------
async def amain():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing")
    bot = Bot(token)
    users = _fetch_all_users()
    log.info("🚀 Worker started — monitoring Freelancer + PPH + Greek feeds")

    while True:
        try:
            for tid in users:
                kws = _fetch_user_keywords(tid)
                log.info(f"[Cycle] User {tid} keywords: {kws}")
                items = _worker.run_pipeline(kws)
                log.info(f"[Worker] run_pipeline returned {len(items)} total jobs")

                # debugging grouping
                from collections import Counter
                srcs = Counter([(it.get("source") or "unknown").lower() for it in items])
                log.info(f"[Worker] Source distribution: {dict(srcs)}")

                sent = 0
                for it in items:
                    key = _job_key(it)
                    if _already_sent(tid, key):
                        continue
                    try:
                        await bot.send_message(
                            chat_id=tid,
                            text=_compose_message(it),
                            parse_mode=ParseMode.HTML,
                            reply_markup=_build_keyboard(_resolve_links(it)),
                            disable_web_page_preview=True
                        )
                        _mark_sent(tid, key)
                        sent += 1
                        await asyncio.sleep(0.4)
                    except Exception as e:
                        log.warning(f"[Send fail] {e}")
                log.info(f"[Worker] Sent {sent} new jobs to {tid}")
        except Exception as e:
            log.error(f"[Main Loop Error] {e}")
        log.info(f"[Sleep] Sleeping {WORKER_INTERVAL}s before next loop…")
        await asyncio.sleep(WORKER_INTERVAL)

if __name__ == "__main__":
    asyncio.run(amain())
