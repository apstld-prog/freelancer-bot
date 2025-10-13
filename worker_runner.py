
#!/usr/bin/env python3
# worker_runner.py — async runner: send-to-all + dedup (PTB v20+)
# Features:
#   - Keyword filtering & "Match: ..." over title+description (from KEYWORDS_CSV)
#   - Budget line shows original currency AND (~ USD) if not USD
#   - "Posted: ..." relative age
#   - job_action_kb(original_url) enforced first so Save works
#   - Dedup safe for legacy constraints

import os, logging, asyncio, inspect, datetime as _dt
from typing import Dict, List, Optional, Set

import worker as _worker
from sqlalchemy import text as _sql_text
from db import get_session as _get_session

# FX conversion reuse
try:
    from utils_fx import load_fx_rates, to_usd as _to_usd
    from config import FX_USD_RATES as _FX_URL
    _RATES = load_fx_rates(_FX_URL)
except Exception:
    _RATES, _to_usd = {}, lambda x, c, r=None: None

# Project keyboard
try:
    from ui_keyboards import job_action_kb as _job_kb
except Exception:
    _job_kb = None

from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
log = logging.getLogger("worker")

def _get_env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, default)).strip())
    except Exception:
        return default

# ---------- keywords ----------
def _env_keywords() -> List[str]:
    csv = os.getenv("KEYWORDS_CSV", "").strip()
    return [w.strip() for w in csv.split(",") if w.strip()]

def _text_contains_any(text: str, words: List[str]) -> Optional[str]:
    if not words:
        return None
    hay = (text or "").lower()
    for w in words:
        if w.lower() in hay:
            return w
    return None

def _detect_match(it: Dict, words: List[str]) -> Optional[str]:
    # explicit match provided by pipeline?
    for k in ("match", "matched", "match_keyword"):
        v = it.get(k)
        if v:
            return str(v)
    # env keywords check over title+description
    title = it.get("title", "")
    desc  = it.get("description", "")
    return _text_contains_any(f"{title}\n{desc}", words)

# ---------- sent_job helpers (no constraint changes) ----------
def _ensure_sent_schema():
    with _get_session() as s:
        s.execute(_sql_text("""
            CREATE TABLE IF NOT EXISTS sent_job (
                chat_id BIGINT,
                user_id BIGINT,
                job_key TEXT,
                sent_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
            );
        """))
        s.execute(_sql_text("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_schema='public' AND table_name='sent_job' AND column_name='chat_id')
                THEN ALTER TABLE sent_job ADD COLUMN chat_id BIGINT; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_schema='public' AND table_name='sent_job' AND column_name='user_id')
                THEN ALTER TABLE sent_job ADD COLUMN user_id BIGINT; END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_schema='public' AND table_name='sent_job' AND column_name='job_key')
                THEN ALTER TABLE sent_job ADD COLUMN job_key TEXT; END IF;
            END $$;
        """))
        s.commit()
    log.info("[dedup] sent_job ensured")

def _already_sent(_uid: int, job_key: str) -> bool:
    with _get_session() as s:
        row = s.execute(_sql_text("SELECT 1 FROM sent_job WHERE job_key=:k LIMIT 1;"), {"k": job_key}).fetchone()
        return row is not None

def _mark_sent(uid: int, job_key: str):
    with _get_session() as s:
        # try ON CONFLICT by job_key (if exists), otherwise check then insert
        try:
            s.execute(_sql_text("INSERT INTO sent_job (chat_id, job_key) VALUES (:u, :k) ON CONFLICT (job_key) DO NOTHING;"),
                     {"u": uid, "k": job_key})
            s.commit()
            return
        except Exception:
            s.rollback()
        try:
            row = s.execute(_sql_text("SELECT 1 FROM sent_job WHERE job_key=:k LIMIT 1;"), {"k": job_key}).fetchone()
            if row is None:
                s.execute(_sql_text("INSERT INTO sent_job (chat_id, job_key) VALUES (:u, :k)"), {"u": uid, "k": job_key})
                s.commit()
        except Exception:
            s.rollback()

# ---------- time helpers ----------
def _parse_timestamp(val) -> Optional[_dt.datetime]:
    if val is None:
        return None
    try:
        if isinstance(val, (int, float)):
            return _dt.datetime.fromtimestamp(float(val), tz=_dt.timezone.utc)
        s = str(val).strip()
        try:
            dt = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_dt.timezone.utc)
            return dt.astimezone(_dt.timezone.utc)
        except Exception:
            pass
        if s.isdigit():
            return _dt.datetime.fromtimestamp(int(s), tz=_dt.timezone.utc)
    except Exception:
        return None
    return None

def _posted_ago(it: Dict) -> Optional[str]:
    if os.getenv("SHOW_RELATIVE_AGE", "on").lower() in ("0","off","false","no"):
        return None
    for key in ("posted_at","created_at","published_at","date","timestamp","ts"):
        dt = _parse_timestamp(it.get(key))
        if dt:
            now = _dt.datetime.now(_dt.timezone.utc)
            diff = now - dt
            secs = int(diff.total_seconds())
            if secs < 60: return f"{secs}s ago"
            mins = secs // 60
            if mins < 60: return f"{mins}m ago"
            hours = mins // 60
            if hours < 24: return f"{hours}h ago"
            days = hours // 24
            return f"{days}d ago"
    return None

# ---------- FX helpers ----------
def _fmt_amount(val) -> Optional[str]:
    try:
        if val is None:
            return None
        if float(val).is_integer():
            return f"{int(float(val))}"
        return f"{float(val):.1f}"
    except Exception:
        return None

def _usd(amount, currency) -> Optional[float]:
    if amount is None or not currency:
        return None
    try:
        if currency.upper() == "USD":
            return float(amount)
        return float(_to_usd(amount, currency, _RATES))
    except Exception:
        return None

def _budget_line(it: Dict) -> Optional[str]:
    cur = (it.get("currency") or "").upper().strip()
    bmin, bmax = it.get("budget_min"), it.get("budget_max")
    if bmin is None and bmax is None:
        return None

    def with_cur(x):
        s = _fmt_amount(x)
        return f"{s} {cur}".strip() if s else None

    if bmin is not None and bmax is not None:
        orig = f"{with_cur(bmin)}–{with_cur(bmax)}" if cur else f"{_fmt_amount(bmin)}–{_fmt_amount(bmax)}"
    elif bmin is not None:
        orig = f"from {with_cur(bmin) if cur else _fmt_amount(bmin)}"
    else:
        orig = f"up to {with_cur(bmax) if cur else _fmt_amount(bmax)}"

    if cur and cur != "USD":
        umin = _usd(bmin, cur) if bmin is not None else None
        umax = _usd(bmax, cur) if bmax is not None else None
        if umin is not None or umax is not None:
            if umin is not None and umax is not None:
                usd = f"(~ {int(round(umin))}–{int(round(umax))} USD)"
            elif umin is not None:
                usd = f"(~ {int(round(umin))} USD)"
            else:
                usd = f"(~ {int(round(umax))} USD)"
            return f"{orig} {usd}"
    return orig

# ---------- compose + keyboard ----------
def _compose_message(it: Dict, words: List[str]) -> str:
    title = (it.get("title") or "").strip() or "Untitled"
    desc = (it.get("description") or "").strip()
    if len(desc) > 700:
        desc = desc[:700] + "…"
    src = it.get("source", "freelancer")

    lines = [f"<b>{title}</b>"]

    bl = _budget_line(it)
    if bl:
        lines.append(f"💰 <i>{bl}</i>")

    if desc:
        lines.append(desc)

    m = _detect_match(it, words)
    if m:
        lines.append(f"Match: {m}")

    age = _posted_ago(it)
    if age:
        lines.append(f"Posted: {age}")

    lines.append(f"🏷️ <i>{src}</i>")
    return "\n".join(lines)

def _resolve_links(it: Dict) -> Dict[str, Optional[str]]:
    original = it.get("original_url") or it.get("url") or ""
    proposal = it.get("proposal_url") or original or ""
    affiliate = it.get("affiliate_url") or ""
    if (it.get("source") or "").lower() == "freelancer" and original and not affiliate:
        try:
            affiliate = _worker.wrap_freelancer(original)
        except Exception:
            pass
    return {"original": original, "proposal": proposal, "affiliate": affiliate}

def _build_keyboard(it: Dict, links: Dict[str, Optional[str]]):
    if _job_kb is not None:
        # force original_url first to satisfy your handler
        try:
            return _job_kb(links["original"])
        except TypeError:
            pass
        except Exception as e:
            log.warning("job_action_kb(original_url) raised: %s", e)
        # try 3-url variant
        try:
            return _job_kb(links["original"], links["proposal"], links["affiliate"])
        except TypeError:
            pass
        except Exception as e:
            log.warning("job_action_kb(3 urls) raised: %s", e)
        # try item variant
        try:
            return _job_kb(it)
        except TypeError:
            pass
        except Exception as e:
            log.warning("job_action_kb(item) raised: %s", e)

    # fallback keyboard (same labels)
    row1 = [
        InlineKeyboardButton("📝 Proposal", url=links["proposal"] or links["original"] or ""),
        InlineKeyboardButton("🔗 Original",  url=links["original"] or ""),
    ]
    row2 = [
        InlineKeyboardButton("⭐ Save",   callback_data="job:save"),
        InlineKeyboardButton("🗑️ Delete", callback_data="job:delete"),
    ]
    return InlineKeyboardMarkup([row1, row2])

# ---------- users ----------
def _fetch_all_users() -> List[int]:
    ids: Set[int] = set()
    with _get_session() as s:
        try:
            rows = s.execute(_sql_text("""
                SELECT DISTINCT telegram_id
                FROM "user"
                WHERE telegram_id IS NOT NULL
                  AND (COALESCE(is_blocked, false) = false)
                  AND (COALESCE(is_active, true) = true)
            """)).fetchall()
            ids.update(int(r[0]) for r in rows if r[0] is not None)
        except Exception as e:
            log.info("[users] skip 'user': %s", e)
        try:
            rows = s.execute(_sql_text("""
                SELECT DISTINCT telegram_id
                FROM users
                WHERE telegram_id IS NOT NULL
                  AND (COALESCE(is_blocked, false) = false)
            """)).fetchall()
            ids.update(int(r[0]) for r in rows if r[0] is not None)
        except Exception as e:
            log.info("[users] skip 'users': %s", e)
    out = sorted(list(ids))
    log.info("[users] total distinct receivers: %s", len(out))
    return out

# ---------- keys ----------
try:
    from dedup import make_key as _make_key
except Exception:
    _make_key = None

def _job_key(it: Dict) -> str:
    if _make_key:
        try:
            return _make_key(it)
        except Exception:
            pass
    sid = str(it.get("id") or it.get("original_url") or it.get("url") or it.get("title") or "")[:512]
    return f"{it.get('source','unknown')}::{sid}"

# ---------- async send ----------
async def _send_items(bot: Bot, chat_id: int, items: List[Dict], per_user_batch: int, words: List[str], filter_on: bool):
    sent = 0
    for it in items:
        if sent >= per_user_batch:
            break
        # apply keyword filter if enabled
        if filter_on and not _detect_match(it, words):
            continue
        k = _job_key(it)
        if _already_sent(chat_id, k):
            continue
        text = _compose_message(it, words)
        links = _resolve_links(it)
        kb = _build_keyboard(it, links)
        try:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, reply_markup=kb, disable_web_page_preview=False)
        except Exception as e:
            log.warning("send_message failed for %s: %s", chat_id, e)
        _mark_sent(chat_id, k)
        sent += 1
        await asyncio.sleep(0.35)

# ---------- main loop ----------
async def amain():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")

    interval = _get_env_int("WORKER_INTERVAL", 60)
    per_user_batch = _get_env_int("BATCH_PER_TICK", 5)

    _ensure_sent_schema()

    # keywords & filter mode
    words = _env_keywords()
    filter_on = os.getenv("KEYWORD_FILTER_MODE", "on").lower() not in ("0","off","false","no")
    if filter_on:
        log.info("[keywords] filtering is ON with %s words: %s", len(words), words)
    else:
        log.info("[keywords] filtering is OFF")

    # run pipeline with or without keywords (best-effort)
    def _pipeline():
        try:
            return _worker.run_pipeline(words if filter_on else [])
        except TypeError:
            return _worker.run_pipeline()

    bot = Bot(token=token)

    while True:
        try:
            items = await asyncio.to_thread(_pipeline)
            users = await asyncio.to_thread(_fetch_all_users)
            if items and users:
                for uid in users:
                    await _send_items(bot, uid, items, per_user_batch, words, filter_on)
            else:
                if not items:
                    log.info("[pipeline] no items this tick")
                if not users:
                    log.info("[users] no receivers")
        except Exception as e:
            log.error("[runner] pipeline/send error: %s", e)

        await asyncio.sleep(interval)

if __name__ == "__main__":
    asyncio.run(amain())
