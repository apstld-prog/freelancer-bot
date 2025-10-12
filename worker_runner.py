
#!/usr/bin/env python3
# worker_runner.py — async runner: send-to-all + per-user/global dedup (PTB v20+)
# - Safe dedup for legacy schemas (UNIQUE/PK on job_key only)
# - Shows "Match: …" (like /selftest) and "Posted: 3m ago"
# - Uses project's ui_keyboards.job_action_kb when available

import os, logging, asyncio, inspect, datetime as _dt
from typing import Dict, List, Optional, Set

import worker as _worker
from sqlalchemy import text as _sql_text
from sqlalchemy.exc import IntegrityError
from db import get_session as _get_session

# Prefer project keyboard (keeps UI/handlers intact)
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

# ---------- sent_job schema + helpers (robust, non-intrusive) ----------
def _ensure_sent_schema():
    """Ensure sent_job exists with columns for id & job_key. Do not enforce PK to respect legacy data."""
    with _get_session() as s:
        s.execute(_sql_text("""
            CREATE TABLE IF NOT EXISTS sent_job (
                chat_id BIGINT,
                user_id BIGINT,
                job_key TEXT,
                sent_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
            );
        """))
        # Ensure columns exist (no rename/migration of existing data)
        s.execute(_sql_text("""
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='sent_job' AND column_name='chat_id'
                ) THEN ALTER TABLE sent_job ADD COLUMN chat_id BIGINT; END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='sent_job' AND column_name='user_id'
                ) THEN ALTER TABLE sent_job ADD COLUMN user_id BIGINT; END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='sent_job' AND column_name='job_key'
                ) THEN ALTER TABLE sent_job ADD COLUMN job_key TEXT; END IF;
            END $$;
        """))
        s.commit()
    log.info("[dedup] sent_job ensured (no constraint changes)")

def _already_sent(_uid: int, job_key: str) -> bool:
    """Return True if this job_key already exists (handles legacy UNIQUE(job_key))."""
    with _get_session() as s:
        row = s.execute(
            _sql_text("SELECT 1 FROM sent_job WHERE job_key=:k LIMIT 1;"),
            {"k": job_key},
        ).fetchone()
        return row is not None

def _mark_sent(uid: int, job_key: str):
    """Insert row safely; prefer ON CONFLICT on job_key, else fall back to exists-check.
       Never raises (so it can't look like send_message failed)."""
    with _get_session() as s:
        # try upsert by job_key (works if there is PK/UNIQUE on job_key)
        try:
            s.execute(
                _sql_text("INSERT INTO sent_job (chat_id, job_key) VALUES (:u, :k) ON CONFLICT (job_key) DO NOTHING;"),
                {"u": uid, "k": job_key},
            )
            s.commit()
            return
        except Exception:
            s.rollback()
        # fallback: exists then insert
        try:
            row = s.execute(_sql_text("SELECT 1 FROM sent_job WHERE job_key=:k LIMIT 1;"), {"k": job_key}).fetchone()
            if row is None:
                s.execute(_sql_text("INSERT INTO sent_job (chat_id, job_key) VALUES (:u, :k)"), {"u": uid, "k": job_key})
                s.commit()
        except Exception:
            s.rollback()
            # swallow

# ---------- "Match" & "Posted" helpers ----------
def _detect_match(it: Dict) -> Optional[str]:
    for k in ("match", "matched", "match_keyword"):
        v = it.get(k)
        if v:
            return str(v)
    csv = os.getenv("KEYWORDS_CSV", "").strip()
    if not csv:
        return None
    hay = f"{it.get('title','')} {it.get('description','')}".lower()
    for w in [x.strip() for x in csv.split(",") if x.strip()]:
        if w.lower() in hay:
            return w
    return None

def _parse_timestamp(val) -> Optional[_dt.datetime]:
    if val is None:
        return None
    try:
        if isinstance(val, (int, float)):
            return _dt.datetime.fromtimestamp(float(val), tz=_dt.timezone.utc)
        s = str(val).strip()
        # try ISO
        try:
            dt = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_dt.timezone.utc)
            return dt.astimezone(_dt.timezone.utc)
        except Exception:
            pass
        # try integer seconds in string
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
            if secs < 60:
                return f"{secs}s ago"
            mins = secs // 60
            if mins < 60:
                return f"{mins}m ago"
            hours = mins // 60
            if hours < 24:
                return f"{hours}h ago"
            days = hours // 24
            return f"{days}d ago"
    return None

# ---------- compose + keyboard ----------
def _compose_message(it: Dict) -> str:
    title = (it.get("title") or "").strip() or "Untitled"
    desc = (it.get("description") or "").strip()
    if len(desc) > 700:
        desc = desc[:700] + "…"
    src = it.get("source", "freelancer")
    budget_min, budget_max = it.get("budget_min"), it.get("budget_max")
    currency = (it.get("currency") or "").strip()
    budget_str = ""
    if budget_min is not None or budget_max is not None:
        if budget_min is not None and budget_max is not None:
            budget_str = f"{budget_min}–{budget_max} {currency}".strip()
        elif budget_min is not None:
            budget_str = f"from {budget_min} {currency}".strip()
        elif budget_max is not None:
            budget_str = f"up to {budget_max} {currency}".strip()

    lines = [f"<b>{title}</b>"]
    if budget_str:
        lines.append(f"💰 <i>{budget_str}</i>")
    if desc:
        lines.append(desc)

    m = _detect_match(it)
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
        try:
            sig = inspect.signature(_job_kb)
            params = list(sig.parameters.keys())
            if len(params) == 1:
                return _job_kb(it)
            if "item" in params:
                return _job_kb(item=it)
            if len(params) >= 3:
                try:
                    return _job_kb(links["original"], links["proposal"], links["affiliate"])
                except Exception:
                    pass
            return _job_kb({"item": it, **links})
        except Exception as e:
            log.warning("job_action_kb fallback: %s", e)

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
async def _send_items(bot: Bot, chat_id: int, items: List[Dict], per_user_batch: int):
    sent = 0
    for it in items:
        if sent >= per_user_batch:
            break
        k = _job_key(it)
        if _already_sent(chat_id, k):
            continue
        text = _compose_message(it)
        links = _resolve_links(it)
        kb = _build_keyboard(it, links)
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
                disable_web_page_preview=False
            )
        except Exception as e:
            log.warning("send_message failed for %s: %s", chat_id, e)
        # never treat dedup insert as send failure
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

    cleanup = os.getenv("WORKER_CLEANUP_DAYS", "")
    if cleanup and cleanup.lower() not in ("0", "false"):
        try:
            d = int(cleanup)
            log.info("[cleanup] using make_interval days=%s", d)
            _worker._cleanup_old_sent_jobs(d)
            log.info("[Runner] cleanup executed on start (days=%s)", d)
        except Exception as e:
            log.warning("[Runner] cleanup failed: %s", e)

    bot = Bot(token=token)

    while True:
        try:
            items = await asyncio.to_thread(_worker.run_pipeline, [])
            users = await asyncio.to_thread(_fetch_all_users)
            if items and users:
                for uid in users:
                    await _send_items(bot, uid, items, per_user_batch)
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
