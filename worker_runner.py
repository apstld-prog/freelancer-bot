#!/usr/bin/env python3
# worker_runner.py — final autonomous PPH scraper version (no proxy)
import os, logging, asyncio, hashlib
from typing import Dict, List, Optional, Set
from datetime import datetime, timezone, timedelta
from html import escape as _esc

import worker as _worker
from sqlalchemy import text as _sql_text
from db import get_session as _get_session
from db_keywords import list_keywords as _list_keywords
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
log = logging.getLogger("worker")

FRESH_HOURS = int(os.getenv("FRESH_WINDOW_HOURS", "48"))

def _h(s: str) -> str:
    return _esc((s or '').strip(), quote=False)

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
    with _get_session() as s:
        rows = s.execute(_sql_text(
            'SELECT DISTINCT telegram_id FROM "user" WHERE telegram_id IS NOT NULL '
            'AND COALESCE(is_blocked,false)=false AND COALESCE(is_active,true)=true'
        )).fetchall()
        return [int(r[0]) for r in rows if r[0]]

def _fetch_user_keywords(tid: int) -> List[str]:
    try:
        with _get_session() as s:
            row = s.execute(_sql_text('SELECT id FROM "user" WHERE telegram_id=:tid'),
                            {"tid": tid}).fetchone()
            if not row: return []
            kws = _list_keywords(int(row[0])) or []
            return [k.strip() for k in kws if k and k.strip()]
    except Exception:
        return []

def _extract_dt(it: Dict) -> Optional[datetime]:
    for k in ("time_submitted","posted_at","created_at","timestamp","date","pub_date"):
        v = it.get(k)
        if not v: continue
        try:
            if isinstance(v, (int,float)):
                sec = float(v); 
                if sec > 1e12: sec /= 1000.0
                return datetime.fromtimestamp(sec, tz=timezone.utc)
            s = str(v).strip().replace("Z","+00:00")
            return datetime.fromisoformat(s)
        except Exception:
            continue
    return None

def _time_ago(dt: datetime) -> str:
    now = datetime.now(timezone.utc)
    diff = now - dt
    s = int(diff.total_seconds())
    if s < 60: return "just now"
    m = s//60
    if m < 60: return f"{m} min ago"
    h = m//60
    if h < 24: return f"{h} h ago"
    d = h//24
    return f"{d} d ago"

def _compose(it: Dict) -> str:
    title = (it.get("title") or "Untitled").strip()
    desc = (it.get("description") or "").strip()
    if len(desc) > 700: desc = desc[:700]+"…"
    src = (it.get("source") or "Freelancer").capitalize()
    budget = it.get("budget_display") or ""
    dt = _extract_dt(it)
    posted = _time_ago(dt) if dt else ""
    kw = it.get("matched_keyword") or ""
    lines = [f"<b>{_h(title)}</b>"]
    if budget: lines.append(f"<b>Budget:</b> {_h(budget)}")
    if src: lines.append(f"<b>Source:</b> {_h(src)}")
    if posted: lines.append(f"<b>Posted:</b> {_h(posted)}")
    if kw: lines.append(f"<b>Match:</b> {_h(kw)}")
    if desc: lines.append(_h(desc))
    return "\n".join(lines)

def _kb(it: Dict):
    o = it.get("original_url") or it.get("url") or ""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Proposal", url=o),
         InlineKeyboardButton("🔗 Original", url=o)],
        [InlineKeyboardButton("⭐ Save", callback_data="job:save"),
         InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")]
    ])

def _job_key(it: Dict) -> str:
    base = it.get("url") or it.get("original_url") or it.get("title") or ""
    return hashlib.sha1(base.encode("utf-8","ignore")).hexdigest()

async def _send(bot: Bot, tid: int, items: List[Dict], batch: int):
    sent = 0
    for it in items:
        if sent >= batch: break
        key = _job_key(it)
        if _already_sent(tid, key): continue
        try:
            await bot.send_message(tid, _compose(it), parse_mode=ParseMode.HTML,
                                   reply_markup=_kb(it), disable_web_page_preview=True)
            _mark_sent(tid, key)
            sent += 1
            await asyncio.sleep(0.4)
        except Exception as e:
            log.warning("send fail %s: %s", tid, e)

async def amain():
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    if not token: raise RuntimeError("TELEGRAM_BOT_TOKEN required")
    interval = int(os.getenv("WORKER_INTERVAL", "120"))
    batch = int(os.getenv("BATCH_PER_TICK", "5"))
    bot = Bot(token)
    users = _fetch_all_users()
    while True:
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=FRESH_HOURS)
            for tid in users:
                kws = _fetch_user_keywords(tid)
                items = _worker.run_pipeline(kws)
                fresh = []
                for it in items:
                    mk = it.get("matched_keyword")
                    if kws and not mk:
                        hay = f"{(it.get('title') or '').lower()} {(it.get('description') or '').lower()}"
                        for k in kws:
                            if (k or '').strip().lower() in hay:
                                mk = k; break
                    if kws and not mk: continue
                    if mk: it["matched_keyword"] = mk
                    dt = _extract_dt(it) or datetime.now(timezone.utc)
                    if dt < cutoff: continue
                    fresh.append(it)
                fresh.sort(key=lambda x: _extract_dt(x) or cutoff, reverse=True)
                if fresh:
                    await _send(bot, tid, fresh, batch)
        except Exception as e:
            log.error("[runner] error: %s", e)
        await asyncio.sleep(interval)

if __name__ == "__main__":
    asyncio.run(amain())
