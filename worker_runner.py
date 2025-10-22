#!/usr/bin/env python3
# worker_runner.py — unified runner (Freelancer + PPH + Greek feeds)
# Includes robust USD conversion fallback in card rendering.

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

# --- intervals (env) ---
FRESH_HOURS = int(os.getenv("FRESH_WINDOW_HOURS", "48"))
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "180"))             # default
FREELANCER_INTERVAL = int(os.getenv("FREELANCER_INTERVAL", "3600"))    # per-source
PPH_INTERVAL        = int(os.getenv("PPH_INTERVAL", "300"))
GREEK_INTERVAL      = int(os.getenv("GREEK_INTERVAL", "300"))

_last_sent_at: Dict[str, float] = {"freelancer": 0.0, "peopleperhour": 0.0, "skywalker": 0.0}

# --- helpers ---
def _now_utc() -> datetime: return datetime.now(timezone.utc)
def _h(s: str) -> str: return _esc((s or '').strip(), quote=False)

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
        rows = s.execute(_sql_text('SELECT DISTINCT telegram_id FROM "user" WHERE telegram_id IS NOT NULL AND COALESCE(is_blocked,false)=false AND COALESCE(is_active,true)=true')).fetchall()
        ids.update(int(r[0]) for r in rows if r[0] is not None)
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

def _to_dt(val) -> Optional[datetime]:
    if val is None: return None
    try:
        if isinstance(val,(int,float)):
            sec=float(val); 
            if sec>1e12: sec/=1000.0
            return datetime.fromtimestamp(sec,tz=timezone.utc)
        s=str(val).strip()
        if s.isdigit():
            sec=int(s); 
            if sec>1e12: sec/=1000.0
            return datetime.fromtimestamp(sec,tz=timezone.utc)
        s2=s.replace("Z","+00:00")
        for fmt in ("%Y-%m-%dT%H:%M:%S%z","%Y-%m-%d %H:%M:%S%z","%Y-%m-%dT%H:%M:%S.%f%z",
                    "%Y-%m-%d %H:%M:%S","%Y-%m-%dT%H:%M:%S","%a, %d %b %Y %H:%M:%S %z"):
            try:
                dt=datetime.strptime(s2,fmt)
                if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
                else: dt = dt.astimezone(timezone.utc)
                return dt
            except Exception: pass
    except Exception: return None
    return None

def _extract_dt(it: Dict) -> Optional[datetime]:
    for k in ("time_submitted","posted_at","created_at","timestamp","date","pub_date","published"):
        dt=_to_dt(it.get(k))
        if dt: return dt
    return None

def _time_ago(dt: datetime) -> str:
    now = _now_utc(); delta = now - dt
    s = int(delta.total_seconds())
    if s < 60: return "just now"
    m = s // 60
    if m < 60: return f"{m} minute{'s' if m!=1 else ''} ago"
    h = m // 60
    if h < 24: return f"{h} hour{'s' if h!=1 else ''} ago"
    d = h // 24
    return f"{d} day{'s' if d!=1 else ''} ago"

# ---- USD fallback table (used only if worker didn't compute *_usd) ----
_FX_FALLBACK = {
    "USD": 1.00, "EUR": 1.08, "GBP": 1.26, "AUD": 0.65, "CAD": 0.73,
    "INR": 0.012, "JPY": 0.0066, "RUB": 0.011, "TRY": 0.030,
}

def _to_usd_fallback(amount, ccy: str):
    try:
        if amount is None: return None
        rate = _FX_FALLBACK.get((ccy or "USD").upper())
        if not rate: return None
        v = float(amount) * rate
        return round(v, 1)
    except Exception:
        return None

def _fmt_num(v):
    try:
        f=float(v); s=f"{f:.1f}"; return s.rstrip("0").rstrip(".")
    except Exception:
        return str(v)

def _compose_message(it: Dict) -> str:
    title = (it.get("title") or "").strip() or "Untitled"
    desc = (it.get("description") or "").strip()
    if len(desc) > 700: desc = desc[:700] + "…"
    src = (it.get("source") or "Freelancer").strip() or "Freelancer"

    display_ccy = it.get("currency_display") or it.get("budget_currency") or it.get("original_currency") or it.get("currency_code_detected") or it.get("currency") or "USD"
    ccy_up = (str(display_ccy).upper() if display_ccy else "USD")

    budget_min = it.get("budget_min"); budget_max = it.get("budget_max")
    usd_min = it.get("budget_min_usd"); usd_max = it.get("budget_max_usd")

    # 💡 NEW: compute USD via fallback if worker didn't provide it
    if usd_min is None and budget_min is not None:
        usd_min = _to_usd_fallback(budget_min, ccy_up)
    if usd_max is None and budget_max is not None:
        usd_max = _to_usd_fallback(budget_max, ccy_up)

    orig = ""
    if budget_min is not None and budget_max is not None: orig = f"{_fmt_num(budget_min)}–{_fmt_num(budget_max)} {display_ccy}"
    elif budget_min is not None: orig = f"from {_fmt_num(budget_min)} {display_ccy}"
    elif budget_max is not None: orig = f"up to {_fmt_num(budget_max)} {display_ccy}"

    usd_hint = ""
    # show USD hint if non-USD OR worker/fallback computed different values
    show_usd = (ccy_up != "USD") and (usd_min is not None or usd_max is not None)
    if show_usd:
        if usd_min is not None and usd_max is not None: usd_hint = f" (~${_fmt_num(usd_min)}–${_fmt_num(usd_max)} USD)"
        elif usd_min is not None: usd_hint = f" (~${_fmt_num(usd_min)} USD)"
        elif usd_max is not None: usd_hint = f" (~${_fmt_num(usd_max)} USD)"

    lines = [f"<b>{_h(title)}</b>"]
    if orig or usd_hint: lines.append(f"<b>Budget:</b> {_h((orig + usd_hint).strip())}")
    lines.append(f"<b>Source:</b> {_h(src)}")

    dt = _extract_dt(it)
    if dt: lines.append(f"<i>{_h(_time_ago(dt))}</i>")

    mk = it.get("matched_keyword") or it.get("match") or it.get("keyword")
    if mk: lines.append(f"<b>Match:</b> {_h(mk)}")
    if desc: lines.append(_h(desc))
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

def _resolve_links(it: Dict) -> Dict[str, Optional[str]]:
    original = it.get("original_url") or it.get("url") or ""
    proposal = it.get("proposal_url") or original or ""
    affiliate = it.get("affiliate_url") or ""
    return {"original": original, "proposal": proposal, "affiliate": affiliate}

def _job_key(it: Dict) -> str:
    base = (it.get("url") or it.get("original_url") or "").strip()
    if not base: base = f"{it.get('source','')}::{(it.get('title') or '')[:160]}"
    return hashlib.sha1(base.encode("utf-8","ignore")).hexdigest()

# -------- interleave per source --------
def interleave_by_source(items: List[Dict]) -> List[Dict]:
    from collections import deque
    buckets = {}
    for it in items:
        src = (it.get("source") or "freelancer").lower()
        buckets.setdefault(src, []).append(it)
    dqs = {src: deque(lst) for src, lst in buckets.items()}
    order = list(dqs.keys())
    out: List[Dict] = []
    while True:
        progressed = False
        for src in order:
            if dqs[src]:
                out.append(dqs[src].popleft()); progressed = True
        if not progressed: break
    return out

async def _send_items(bot: Bot, chat_id: int, items: List[Dict], per_user_batch: int):
    sent = 0
    for it in items:
        if sent >= per_user_batch: break
        key = _job_key(it)
        if _already_sent(chat_id, key): continue
        try:
            await bot.send_message(chat_id=chat_id, text=_compose_message(it),
                                   parse_mode=ParseMode.HTML,
                                   reply_markup=_build_keyboard(_resolve_links(it)),
                                   disable_web_page_preview=True)
            _mark_sent(chat_id, key)
            sent += 1
            await asyncio.sleep(0.35)
        except Exception as e:
            log.warning("send_message failed for %s: %s", chat_id, e)

# ---------- fetchers ----------
def _should_run(tag: str, interval_sec: int) -> bool:
    import time
    now = time.time()
    if now - _last_sent_at.get(tag, 0.0) >= interval_sec:
        _last_sent_at[tag] = now
        return True
    return False

def _gather_items(keywords: List[str]) -> List[Dict]:
    # keep using the existing worker pipeline (it already merges + prepares)
    try:
        items = _worker.run_pipeline(keywords)
    except Exception as e:
        log.warning("worker.run_pipeline failed: %s", e)
        items = []
    return items

async def amain():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")
    per_user_batch = int(os.getenv("BATCH_PER_TICK", "5"))
    bot = Bot(token=token)

    users = _fetch_all_users()
    log.info("🚀 Starting unified worker (Freelancer + PPH + Greek feeds)")

    while True:
        try:
            cutoff = _now_utc() - timedelta(hours=FRESH_HOURS)
            for tid in users:
                kws = _fetch_user_keywords(tid)
                items = _gather_items(kws)

                filtered: List[Dict] = []
                for it in items:
                    mk = it.get("matched_keyword")
                    if not mk:
                        hay = f"{(it.get('title') or '').lower()}\n{(it.get('description') or '').lower()}"
                        for kw in kws:
                            if (kw or '').strip().lower() in hay:
                                mk = kw; break
                    if kws and not mk:
                        continue
                    if mk: it["matched_keyword"] = mk
                    dt = _extract_dt(it)
                    if not dt or dt < cutoff:
                        continue
                    filtered.append(it)

                filtered.sort(key=lambda x: _extract_dt(x) or cutoff, reverse=True)
                mixed = interleave_by_source(filtered)
                if mixed:
                    await _send_items(bot, tid, mixed, per_user_batch)
        except Exception as e:
            log.error("[runner] pipeline error: %s", e)
        await asyncio.sleep(WORKER_INTERVAL)

if __name__ == "__main__":
    asyncio.run(amain())
