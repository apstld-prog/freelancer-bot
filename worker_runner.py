#!/usr/bin/env python3
# worker_runner.py — FINAL BUILD: unified pipeline (Freelancer + PPH + GR sources)
import os, asyncio, logging, hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set
from html import escape as _esc

import worker as _worker
from sqlalchemy import text as _sql_text
from db import get_session as _get_session
from db_keywords import list_keywords as _list_keywords

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper()))
log = logging.getLogger("worker")

# window
FRESH_HOURS = int(os.getenv("FRESH_WINDOW_HOURS", "48"))
INTERVAL = int(os.getenv("WORKER_INTERVAL", "120"))
PER_USER_BATCH = int(os.getenv("BATCH_PER_TICK", "5"))
ENABLE_PPH = os.getenv("ENABLE_PPH", "1") == "1"

# ---------- helpers ----------
def _esc_html(x: str) -> str:
    return _esc((x or "").strip(), quote=False)

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
    _ensure_sent_table()
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
            'SELECT DISTINCT telegram_id FROM "user" WHERE telegram_id IS NOT NULL AND COALESCE(is_blocked,false)=false AND COALESCE(is_active,true)=true'
        )).fetchall()
    return [int(r[0]) for r in rows if r[0]]

def _keywords_for(uid: int) -> List[str]:
    try:
        with _get_session() as s:
            row = s.execute(_sql_text('SELECT id FROM "user" WHERE telegram_id=:tid'), {"tid": uid}).fetchone()
            if not row:
                return []
            kid = int(row[0])
        return [k.strip() for k in _list_keywords(kid) if k and k.strip()]
    except Exception:
        return []

def _job_key(it: Dict) -> str:
    base = (it.get("url") or it.get("original_url") or it.get("affiliate_url") or "").strip()
    if not base:
        base = f"{it.get('source','')}::{(it.get('title') or '')}"
    return hashlib.sha1(base.encode("utf-8", "ignore")).hexdigest()

def _to_dt(v) -> Optional[datetime]:
    if not v:
        return None
    try:
        if isinstance(v, (int, float)):
            if v > 1e12: v /= 1000.0
            return datetime.fromtimestamp(v, tz=timezone.utc)
        s = str(v).replace("Z", "+00:00")
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z",
                    "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(s, fmt)
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

def _extract_dt(it: Dict) -> Optional[datetime]:
    for k in ("time_submitted", "posted_at", "created_at", "timestamp", "date"):
        dt = _to_dt(it.get(k))
        if dt:
            return dt
    return None

def _ago(dt: datetime) -> str:
    delta = datetime.now(timezone.utc) - dt
    s = int(delta.total_seconds())
    if s < 60:
        return "just now"
    m = s // 60
    if m < 60:
        return f"{m} minute{'s' if m!=1 else ''} ago"
    h = m // 60
    if h < 24:
        return f"{h} hour{'s' if h!=1 else ''} ago"
    d = h // 24
    return f"{d} day{'s' if d!=1 else ''} ago"

def _compose(it: Dict) -> str:
    title = (it.get("title") or "Untitled").strip()
    desc = (it.get("description") or "").strip()
    if len(desc) > 700:
        desc = desc[:700] + "…"
    src = (it.get("source") or "Freelancer").strip()

    cur = it.get("budget_currency") or it.get("currency") or "USD"
    bmin, bmax = it.get("budget_min"), it.get("budget_max")
    usdmin, usdmax = it.get("budget_min_usd"), it.get("budget_max_usd")

    def fmt(x): 
        try:
            f = float(x); s = f"{f:.1f}"; return s.rstrip("0").rstrip(".")
        except: 
            return str(x)

    line = f"<b>{_esc_html(title)}</b>"
    btxt = ""
    if bmin and bmax: btxt = f"{fmt(bmin)}–{fmt(bmax)} {cur}"
    elif bmin: btxt = f"from {fmt(bmin)} {cur}"
    elif bmax: btxt = f"up to {fmt(bmax)} {cur}"
    if btxt: line += f"\n<b>Budget:</b> {_esc_html(btxt)}"
    if usdmin or usdmax:
        if usdmin and usdmax: line += f" (~${fmt(usdmin)}–${fmt(usdmax)} USD)"
        elif usdmin: line += f" (~${fmt(usdmin)} USD)"
        elif usdmax: line += f" (~${fmt(usdmax)} USD)"

    line += f"\n<b>Source:</b> {_esc_html(src)}"
    dt = _extract_dt(it)
    if dt: line += f"\n<b>Posted:</b> {_esc_html(_ago(dt))}"
    if it.get("matched_keyword"):
        line += f"\n<b>Match:</b> {_esc_html(it['matched_keyword'])}"
    if desc:
        line += f"\n{_esc_html(desc)}"
    return line

def _links(it: Dict):
    url = it.get("original_url") or it.get("url") or ""
    aff = it.get("affiliate_url") or url
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Proposal", url=aff),
         InlineKeyboardButton("🔗 Original", url=url)],
        [InlineKeyboardButton("⭐ Save", callback_data="job:save"),
         InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")],
    ])

def _merge_items(kws: List[str]) -> List[Dict]:
    items = []
    try:
        items.extend(_worker.run_pipeline(kws))
    except Exception as e:
        log.warning("Freelancer pipeline error: %s", e)

    if ENABLE_PPH:
        try:
            import platform_peopleperhour as pph
            extra = pph.get_items(kws)
            log.info("PPH merged: %d items", len(extra))
            items.extend(extra)
        except Exception as e:
            log.warning("PPH error: %s", e)
    return items

def interleave(items: List[Dict]) -> List[Dict]:
    from collections import deque
    groups = {}
    for it in items:
        src = (it.get("source") or "freelancer").lower()
        groups.setdefault(src, []).append(it)
    dq = {k: deque(v) for k, v in groups.items()}
    out = []
    while True:
        moved = False
        for src in dq:
            if dq[src]:
                out.append(dq[src].popleft())
                moved = True
        if not moved:
            break
    return out

async def send_items(bot: Bot, uid: int, items: List[Dict]):
    sent = 0
    for it in items:
        if sent >= PER_USER_BATCH:
            break
        key = _job_key(it)
        if _was_sent(uid, key):
            continue
        try:
            await bot.send_message(
                chat_id=uid,
                text=_compose(it),
                parse_mode=ParseMode.HTML,
                reply_markup=_links(it),
                disable_web_page_preview=True,
            )
            _mark_sent(uid, key)
            sent += 1
            await asyncio.sleep(0.4)
        except Exception as e:
            log.warning("send to %s failed: %s", uid, e)

# ---------- main ----------
async def amain():
    token = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN missing")

    bot = Bot(token=token)
    users = _fetch_users()
    log.info("Fetched %d users", len(users))

    while True:
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=FRESH_HOURS)
            for uid in users:
                kws = _keywords_for(uid)
                items = _merge_items(kws)
                fresh = []
                for it in items:
                    mk = it.get("matched_keyword")
                    if not mk:
                        text = f"{(it.get('title') or '').lower()} {(it.get('description') or '').lower()}"
                        for kw in kws:
                            if kw.lower() in text:
                                mk = kw
                                break
                    if not mk:
                        continue
                    it["matched_keyword"] = mk
                    dt = _extract_dt(it)
                    if not dt or dt < cutoff:
                        continue
                    fresh.append(it)
                fresh.sort(key=lambda x: _extract_dt(x) or cutoff, reverse=True)
                mixed = interleave(fresh)
                if mixed:
                    await send_items(bot, uid, mixed)
        except Exception as e:
            log.error("Main loop error: %s", e)
        await asyncio.sleep(INTERVAL)

if __name__ == "__main__":
    asyncio.run(amain())
