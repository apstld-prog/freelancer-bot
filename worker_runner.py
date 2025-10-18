#!/usr/bin/env python3
# worker_runner.py — per-user fetch, keyword-only filter, DB dedup, correct budget formatting

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

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
log = logging.getLogger("worker")

def _h(s: str) -> str:
    return _esc((s or '').strip(), quote=False)

# ============ DB: sent dedup ============
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

# ============ Users / Keywords ============
def _fetch_all_users() -> List[int]:
    ids: Set[int] = set()
    with _get_session() as s:
        try:
            rows = s.execute(_sql_text("""
                SELECT DISTINCT telegram_id
                FROM "user"
                WHERE telegram_id IS NOT NULL
                  AND COALESCE(is_blocked,false)=false
                  AND COALESCE(is_active,true)=true
            """)).fetchall()
            ids.update(int(r[0]) for r in rows if r[0] is not None)
        except Exception:
            pass
        try:
            rows = s.execute(_sql_text("""
                SELECT DISTINCT telegram_id
                FROM users
                WHERE telegram_id IS NOT NULL
                  AND COALESCE(is_blocked,false)=false
            """)).fetchall()
            ids.update(int(r[0]) for r in rows if r[0] is not None)
        except Exception:
            pass
    return sorted(list(ids))

def _fetch_user_keywords(telegram_id: int) -> List[str]:
    try:
        with _get_session() as s:
            row = s.execute(_sql_text('SELECT id FROM "user" WHERE telegram_id=:tid'), {"tid": telegram_id}).fetchone()
            if not row: return []
            uid = int(row[0])
        kws = _list_keywords(uid) or []
        return [k.strip() for k in kws if k and k.strip()]
    except Exception:
        return []

def _find_match_keyword(it: Dict, kws: List[str]) -> Optional[str]:
    if not kws: return None
    hay = f"{(it.get('title') or '').lower()}\n{(it.get('description') or '').lower()}"
    for kw in kws:
        if (kw or "").strip().lower() in hay:
            return kw  # keep original casing
    return None

# ============ Time helpers ============
def _to_dt(val) -> Optional[datetime]:
    """Best-effort convert various timestamp formats to aware UTC datetime."""
    if val is None:
        return None
    try:
        # numeric epoch seconds or milliseconds
        if isinstance(val, (int, float)):
            sec = float(val)
            if sec > 1e12:  # likely ms
                sec /= 1000.0
            return datetime.fromtimestamp(sec, tz=timezone.utc)
        # strings
        s = str(val).strip()
        # try integer string
        if s.isdigit():
            sec = int(s)
            if sec > 1e12:
                sec /= 1000.0
            return datetime.fromtimestamp(sec, tz=timezone.utc)
        # normalize Z
        s2 = s.replace("Z", "+00:00")
        # common ISO formats
        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
        ):
            try:
                dt = datetime.strptime(s2, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                return dt
            except Exception:
                pass
    except Exception:
        return None
    return None

def _time_ago_from_item(it: Dict) -> Optional[str]:
    """Return 'X minutes ago' style string if we can parse a timestamp from the item."""
    ts = (
        it.get("time_submitted")
        or it.get("posted_at")
        or it.get("created_at")
        or it.get("timestamp")
        or it.get("date")
    )
    dt = _to_dt(ts)
    if not dt:
        return None
    now = datetime.now(timezone.utc)
    delta: timedelta = now - dt
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    if days < 30:
        return f"{days} day{'s' if days != 1 else ''} ago"
    months = days // 30
    if months < 12:
        return f"{months} month{'s' if months != 1 else ''} ago"
    years = months // 12
    return f"{years} year{'s' if years != 1 else ''} ago"

# ============ Message compose ============
def _compose_message(it: Dict) -> str:
    title = (it.get("title") or "").strip() or "Untitled"
    desc = (it.get("description") or "").strip()
    if len(desc) > 700:
        desc = desc[:700] + "…"
    src = (it.get("source") or "Freelancer").strip() or "Freelancer"

    display_ccy = (
        it.get("currency_display")
        or it.get("budget_currency")
        or it.get("original_currency")
        or it.get("currency_code_detected")
        or it.get("currency")
        or "USD"
    )

    budget_min = it.get("budget_min")
    budget_max = it.get("budget_max")
    usd_min = it.get("budget_min_usd")
    usd_max = it.get("budget_max_usd")

    def _fmt(v):
        try:
            f = float(v)
            s = f"{f:.1f}"
            return s.rstrip("0").rstrip(".")
        except Exception:
            return str(v)

    # Build original budget label
    orig = ""
    if budget_min is not None and budget_max is not None:
        orig = f"{_fmt(budget_min)}–{_fmt(budget_max)} {display_ccy}".strip()
    elif budget_min is not None:
        orig = f"from {_fmt(budget_min)} {display_ccy}".strip()
    elif budget_max is not None:
        orig = f"up to {_fmt(budget_max)} {display_ccy}".strip()

    # USD hint
    usd_hint = ""
    if usd_min is not None and usd_max is not None:
        usd_hint = f" (~${_fmt(usd_min)}–${_fmt(usd_max)} USD)"
    elif usd_min is not None:
        usd_hint = f" (~${_fmt(usd_min)} USD)"
    elif usd_max is not None:
        usd_hint = f" (~${_fmt(usd_max)} USD)"

    budget_str = (orig + usd_hint).strip()

    lines: List[str] = [f"<b>{_h(title)}</b>"]
    if budget_str:
        lines.append(f"<b>Budget:</b> {_h(budget_str)}")
    lines.append(f"<b>Source:</b> {_h(src)}")

    # NEW: relative time if available
    rel = _time_ago_from_item(it)
    if rel:
        lines.append(f"<b>Posted:</b> {_h(rel)}")

    mk = it.get("matched_keyword") or it.get("match") or it.get("keyword")
    if mk:
        lines.append(f"<b>Match:</b> {_h(mk)}")
    if desc:
        lines.append(_h(desc))
    return "\n".join([ln for ln in lines if ln])

def _build_keyboard(links: Dict[str, Optional[str]]):
    try:
        from ui_keyboards import job_action_kb as _job_kb
        return _job_kb(links["original"], links["proposal"], links["affiliate"])
    except Exception:
        row1 = [
            InlineKeyboardButton("📄 Proposal", url=(links.get("proposal") or links.get("original") or "")),
            InlineKeyboardButton("🔗 Original", url=(links.get("original") or "")),
        ]
        row2 = [
            InlineKeyboardButton("⭐ Save", callback_data="job:save"),
            InlineKeyboardButton("🗑️ Delete", callback_data="job:delete"),
        ]
        return InlineKeyboardMarkup([row1, row2])

def _resolve_links(it: Dict) -> Dict[str, Optional[str]]:
    original = it.get("original_url") or it.get("url") or ""
    proposal = it.get("proposal_url") or original or ""
    affiliate = it.get("affiliate_url") or ""
    if (it.get("source") or "").lower() == "freelancer" and original and not affiliate:
        try: affiliate = _worker.wrap_freelancer(original)
        except Exception: pass
    return {"original": original, "proposal": proposal, "affiliate": affiliate}

# ============ Send (DB dedup) ============
def _job_key(it: Dict) -> str:
    base = (it.get("url") or it.get("original_url") or "").strip()
    if not base:
        base = f"{it.get('source','')}::{(it.get('title') or '')[:160]}"
    return hashlib.sha1(base.encode("utf-8", "ignore")).hexdigest()

async def _send_items(bot: Bot, chat_id: int, items: List[Dict], per_user_batch: int):
    sent = 0
    for it in items:
        if sent >= per_user_batch:
            break
        key = _job_key(it)
        if _already_sent(chat_id, key):
            continue
        try:
            text = _compose_message(it)
            kb = _build_keyboard(_resolve_links(it))
            await bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML,
                                   reply_markup=kb, disable_web_page_preview=True)
            _mark_sent(chat_id, key)
            sent += 1
            await asyncio.sleep(0.35)
        except Exception as e:
            log.warning("send_message failed for %s: %s", chat_id, e)

# ============ Main loop ============
async def amain():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")
    interval = int(os.getenv("WORKER_INTERVAL", "120"))
    per_user_batch = int(os.getenv("BATCH_PER_TICK", "5"))
    bot = Bot(token=token)
    # Dual-interval settings: Freelancer every 60s (loop), PPH every 600s (10 min)
    pph_interval = int(os.getenv('PPH_INTERVAL_SECONDS', '600'))
    _pph_last_ts: float = 0.0

    while True:
        try:
            users = await asyncio.to_thread(_fetch_all_users)
            if users:
                for tid in users:
                    kws = await asyncio.to_thread(_fetch_user_keywords, tid)
                    # Toggle ENABLE_PPH based on per-platform interval
                    _enable_pph_original = os.getenv('ENABLE_PPH', '0')
                    now_ts = __import__('time').time()
                    _include_pph = False
                    if _enable_pph_original == '1':
                        if (now_ts - _pph_last_ts) >= pph_interval:
                            _include_pph = True
                        else:
                            os.environ['ENABLE_PPH'] = '0'
                    items = await asyncio.to_thread(_worker.run_pipeline, kws)
                    if _enable_pph_original is not None:
                        os.environ['ENABLE_PPH'] = _enable_pph_original
                    if _include_pph:
                        _pph_last_ts = now_ts

                    # ⭐ Filter: keep ONLY items with a keyword match
                    filtered: List[Dict] = []
                    for it in items:
                        mk = it.get("matched_keyword") or _find_match_keyword(it, kws)
                        if kws and not mk:
                            continue  # skip non-matching items
                        if mk:
                            it["matched_keyword"] = mk  # ensure it's visible in message
                        filtered.append(it)

                    if filtered:
                        try:
                            from collections import Counter
                            c = Counter([it.get('source') for it in filtered])
                            log.info("[tick] user=%s sources=%s", tid, dict(c))
                        except Exception:
                            pass
                        await _send_items(bot, tid, filtered, per_user_batch)
        except Exception as e:
            log.error("[runner] pipeline error: %s", e)

        await asyncio.sleep(interval)

if __name__ == "__main__":
    asyncio.run(amain())
