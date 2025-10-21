#!/usr/bin/env python3
# worker_runner.py — FINAL (optimized retry-safe version for PeoplePerHour)
import os
import asyncio
import logging
import hashlib
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set
from html import escape as _esc

import worker as _worker
from sqlalchemy import text as _sql_text
from db import get_session as _get_session
from db_keywords import list_keywords as _list_keywords

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

# ---------- CONFIG ----------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
log = logging.getLogger("worker")

FRESH_HOURS = int(os.getenv("FRESH_WINDOW_HOURS", "48"))
INTERVAL = int(os.getenv("WORKER_INTERVAL", "120"))
PER_USER_BATCH = int(os.getenv("BATCH_PER_TICK", "5"))
ENABLE_PPH = os.getenv("ENABLE_PPH", "1") == "1"

# Optimized safe retry intervals
PPH_RETRY_DELAY_SEC = 45
PPH_RETRY_COOLDOWN_SEC = 900
PPH_RETRY_CONCURRENCY = 3
PPH_MIN_INTERVAL_BETWEEN_REQS = 60

# ---------- Runtime state ----------
_PPH_LAST_RETRY: Dict[str, float] = {}
_PPH_LAST_REQUEST_TIME: float = 0.0
_PPH_RETRY_SEMAPHORE = asyncio.Semaphore(PPH_RETRY_CONCURRENCY)

# ---------- DB ----------
def _ensure_sent_table():
    with _get_session() as s:
        s.execute(_sql_text("""
            CREATE TABLE IF NOT EXISTS sent_job (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                job_key TEXT NOT NULL,
                sent_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC'),
                UNIQUE (user_id, job_key)
            );
        """))
        s.commit()

def _was_sent(uid: int, key: str) -> bool:
    with _get_session() as s:
        row = s.execute(_sql_text("SELECT 1 FROM sent_job WHERE user_id=:u AND job_key=:k LIMIT 1"),
                        {"u": uid, "k": key}).fetchone()
        return bool(row)

def _mark_sent(uid: int, key: str):
    with _get_session() as s:
        s.execute(_sql_text("INSERT INTO sent_job (user_id,job_key) VALUES (:u,:k) ON CONFLICT DO NOTHING"),
                  {"u": uid, "k": key})
        s.commit()

def _fetch_users() -> List[int]:
    with _get_session() as s:
        rows = s.execute(_sql_text(
            'SELECT DISTINCT telegram_id FROM "user" WHERE telegram_id IS NOT NULL '
            'AND COALESCE(is_blocked,false)=false AND COALESCE(is_active,true)=true'
        )).fetchall()
    return [int(r[0]) for r in rows if r[0]]

def _keywords_for_user(telegram_id: int) -> List[str]:
    try:
        with _get_session() as s:
            row = s.execute(_sql_text('SELECT id FROM "user" WHERE telegram_id=:tid'),
                            {"tid": telegram_id}).fetchone()
            if not row:
                return []
            uid = int(row[0])
        return [k.strip() for k in _list_keywords(uid) if k and k.strip()]
    except Exception:
        return []

# ---------- Helpers ----------
def _esc_html(s: str) -> str:
    return _esc((s or "").strip(), quote=False)

def _job_key(it: Dict) -> str:
    base = (it.get("original_url") or it.get("url") or it.get("affiliate_url") or
            (it.get("source", "") + "::" + (it.get("title") or ""))).strip()
    return hashlib.sha1(base.encode("utf-8", "ignore")).hexdigest()

def _to_dt(val) -> Optional[datetime]:
    if val is None:
        return None
    try:
        if isinstance(val, (int, float)):
            sec = float(val)
            if sec > 1e12:
                sec /= 1000.0
            return datetime.fromtimestamp(sec, tz=timezone.utc)
        s = str(val).strip()
        if s.isdigit():
            sec = int(s)
            if sec > 1e12:
                sec /= 1000.0
            return datetime.fromtimestamp(sec, tz=timezone.utc)
        s2 = s.replace("Z", "+00:00")
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z",
                    "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(s2, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                return dt
            except Exception:
                continue
    except Exception:
        return None
    return None

def _time_ago(dt: datetime) -> str:
    now = datetime.now(timezone.utc)
    diff = now - dt
    s = int(diff.total_seconds())
    if s < 60: return "just now"
    m = s // 60
    if m < 60: return f"{m} min ago"
    h = m // 60
    if h < 24: return f"{h} h ago"
    d = h // 24
    return f"{d} d ago"

def _compose_message(it: Dict) -> str:
    title = (it.get("title") or "Untitled").strip()
    desc = (it.get("description") or "").strip()
    if len(desc) > 700:
        desc = desc[:700] + "…"
    src = (it.get("source") or "Freelancer").strip()

    budget_min, budget_max = it.get("budget_min"), it.get("budget_max")
    ccy = it.get("budget_currency") or it.get("currency") or "USD"
    lines = [f"<b>{_esc_html(title)}</b>"]

    if budget_min or budget_max:
        if budget_min and budget_max:
            lines.append(f"<b>Budget:</b> {_esc_html(f'{budget_min}–{budget_max} {ccy}')}")
        elif budget_min:
            lines.append(f"<b>Budget:</b> from {_esc_html(str(budget_min))} {ccy}")
        elif budget_max:
            lines.append(f"<b>Budget:</b> up to {_esc_html(str(budget_max))} {ccy}")

    lines.append(f"<b>Source:</b> {_esc_html(src)}")

    dt = _to_dt(it.get("time_submitted"))
    if dt:
        lines.append(f"<b>Posted:</b> {_esc_html(_time_ago(dt))}")

    mk = it.get("matched_keyword")
    if mk:
        lines.append(f"<b>Match:</b> {_esc_html(mk)}")

    if desc:
        lines.append(_esc_html(desc))

    return "\n".join(lines)

def _keyboard(it: Dict):
    original = it.get("original_url") or ""
    proposal = it.get("proposal_url") or original
    row1 = [
        InlineKeyboardButton("📄 Proposal", url=proposal),
        InlineKeyboardButton("🔗 Original", url=original),
    ]
    row2 = [
        InlineKeyboardButton("⭐ Save", callback_data="job:save"),
        InlineKeyboardButton("🗑️ Delete", callback_data="job:delete"),
    ]
    return InlineKeyboardMarkup([row1, row2])

# ---------- Background retry ----------
async def _pph_retry(keyword: str, bot: Bot, user_ids: List[int]):
    global _PPH_LAST_REQUEST_TIME
    now = asyncio.get_event_loop().time()
    last = _PPH_LAST_RETRY.get(keyword)
    if last and (now - last) < PPH_RETRY_COOLDOWN_SEC:
        log.debug("Skip retry for '%s' (cooldown active)", keyword)
        return

    _PPH_LAST_RETRY[keyword] = now
    await asyncio.sleep(PPH_RETRY_DELAY_SEC)

    async with _PPH_RETRY_SEMAPHORE:
        elapsed = asyncio.get_event_loop().time() - _PPH_LAST_REQUEST_TIME
        if elapsed < PPH_MIN_INTERVAL_BETWEEN_REQS:
            await asyncio.sleep(PPH_MIN_INTERVAL_BETWEEN_REQS - elapsed + random.uniform(0.3, 1.2))

        try:
            import platform_peopleperhour as pph
            results = pph.get_items([keyword])
            _PPH_LAST_REQUEST_TIME = asyncio.get_event_loop().time()
            if not results:
                log.info("Retry found 0 jobs for '%s'", keyword)
                return

            for uid in user_ids:
                sent = 0
                for it in results:
                    if _was_sent(uid, _job_key(it)): continue
                    try:
                        await bot.send_message(chat_id=uid, text=_compose_message(it),
                                               parse_mode=ParseMode.HTML,
                                               reply_markup=_keyboard(it),
                                               disable_web_page_preview=True)
                        _mark_sent(uid, _job_key(it))
                        sent += 1
                        if sent >= PER_USER_BATCH: break
                        await asyncio.sleep(0.4)
                    except Exception as e:
                        log.warning("Retry send failed: %s", e)
        except Exception as e:
            log.warning("PPH retry error for '%s': %s", keyword, e)

# ---------- Main loop ----------
async def amain():
    token = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN missing")

    bot = Bot(token=token)
    users = _fetch_users()
    log.info("Worker start — users=%d", len(users))

    while True:
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=FRESH_HOURS)
            for tid in users:
                kws = _keywords_for_user(tid)
                if not kws: continue
                items = []
                try:
                    items = _worker.run_pipeline(kws)
                    if ENABLE_PPH:
                        import platform_peopleperhour as pph
                        pph_items = pph.get_items(kws)
                        if not pph_items:
                            for kw in kws:
                                asyncio.create_task(_pph_retry(kw, bot, [tid]))
                        items.extend(pph_items)
                except Exception as e:
                    log.warning("Pipeline error: %s", e)

                filtered = []
                for it in items:
                    mk = it.get("matched_keyword")
                    if not mk:
                        for kw in kws:
                            if kw.lower() in (it.get("title", "") + it.get("description", "")).lower():
                                mk = kw; break
                    if not mk: continue
                    it["matched_keyword"] = mk
                    dt = _to_dt(it.get("time_submitted"))
                    if not dt or dt < cutoff: continue
                    filtered.append(it)

                filtered.sort(key=lambda x: _to_dt(x.get("time_submitted")) or cutoff, reverse=True)
                for it in filtered[:PER_USER_BATCH]:
                    if _was_sent(tid, _job_key(it)): continue
                    try:
                        await bot.send_message(chat_id=tid, text=_compose_message(it),
                                               parse_mode=ParseMode.HTML,
                                               reply_markup=_keyboard(it),
                                               disable_web_page_preview=True)
                        _mark_sent(tid, _job_key(it))
                        await asyncio.sleep(0.35)
                    except Exception as e:
                        log.warning("Send error: %s", e)
        except Exception as e:
            log.error("Worker loop error: %s", e)
        await asyncio.sleep(INTERVAL)

if __name__ == "__main__":
    _ensure_sent_table()
    asyncio.run(amain())
