#!/usr/bin/env python3
# worker_runner.py — async runner: send-to-all + per-user dedup (PTB v20+)
# Safer schema handling for sent_job (no PK enforcement; supports chat_id or user_id).

import os, logging, asyncio
from typing import Dict, List, Optional, Set

import worker as _worker
from sqlalchemy import text as _sql_text
from db import get_session as _get_session
from db_keywords import list_keywords as _list_keywords

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

# ---------- sent_job schema + helpers (per-user dedup, robust & non-intrusive) ----------
def _sent_user_col() -> str:
    """Return preferred id column present in sent_job: chat_id > user_id; create chat_id if none exists."""
    with _get_session() as s:
        row = s.execute(_sql_text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='sent_job'
              AND column_name IN ('chat_id','user_id')
            ORDER BY CASE WHEN column_name='chat_id' THEN 0 ELSE 1 END
            LIMIT 1
        """)).fetchone()
        if row:
            return row[0]
        # No id column at all → add chat_id
        s.execute(_sql_text("CREATE TABLE IF NOT EXISTS sent_job (chat_id BIGINT, job_key TEXT, sent_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'));"))
        s.execute(_sql_text("""
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='sent_job' AND column_name='chat_id'
                ) THEN
                    ALTER TABLE sent_job ADD COLUMN chat_id BIGINT;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='sent_job' AND column_name='job_key'
                ) THEN
                    ALTER TABLE sent_job ADD COLUMN job_key TEXT;
                END IF;
            END $$;
        """))
        s.commit()
        return "chat_id"

def _ensure_sent_schema():
    """Ensure table exists and has at least (idcol, job_key, sent_at). Do NOT enforce PK to avoid legacy nulls."""
    with _get_session() as s:
        s.execute(_sql_text("CREATE TABLE IF NOT EXISTS sent_job (chat_id BIGINT, job_key TEXT, sent_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'));"))
        # Ensure both columns exist if possible
        s.execute(_sql_text("""
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='sent_job' AND column_name='chat_id'
                ) THEN
                    ALTER TABLE sent_job ADD COLUMN chat_id BIGINT;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='sent_job' AND column_name='user_id'
                ) THEN
                    ALTER TABLE sent_job ADD COLUMN user_id BIGINT;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='sent_job' AND column_name='job_key'
                ) THEN
                    ALTER TABLE sent_job ADD COLUMN job_key TEXT;
                END IF;
            END $$;
        """))
        s.commit()
    log.info("[dedup] sent_job schema ensured (id column chosen: %s)", _sent_user_col())

def _already_sent(user_id: int, job_key: str) -> bool:
    col = _sent_user_col()
    with _get_session() as s:
        row = s.execute(
            _sql_text(f"SELECT 1 FROM sent_job WHERE {col}=:u AND job_key=:k LIMIT 1;"),
            {"u": user_id, "k": job_key},
        ).fetchone()
        return row is not None

def _mark_sent(user_id: int, job_key: str):
    col = _sent_user_col()
    with _get_session() as s:
        s.execute(
            _sql_text(f"INSERT INTO sent_job ({col}, job_key) VALUES (:u, :k)"),
            {"u": user_id, "k": job_key},
        )
        s.commit()

# ---------- compose + keyboard ----------

def _compose_message(it: Dict) -> str:
    title = (it.get("title") or "").strip() or "Untitled"
    desc = (it.get("description") or "").strip()
    if len(desc) > 700:
        desc = desc[:700] + "…"
    src = it.get("source", "freelancer")
    budget_min, budget_max = it.get("budget_min"), it.get("budget_max")
    currency = (it.get("currency") or "").upper()
    usd_min, usd_max = it.get("budget_min_usd"), it.get("budget_max_usd")
    budget_str = ""
    if currency:
        if budget_min is not None and budget_max is not None:
            orig = f"{budget_min}–{budget_max} {currency}"
            usd = None
            if usd_min is not None and usd_max is not None:
                usd = f"${usd_min}–${usd_max}"
            elif usd_min is not None:
                usd = f"from ${usd_min}"
            elif usd_max is not None:
                usd = f"up to ${usd_max}"
            budget_str = orig + (f" (≈ {usd})" if usd else "")
        elif budget_min is not None:
            orig = f"from {budget_min} {currency}"
            budget_str = orig + (f" (≈ ${usd_min})" if usd_min is not None else "")
        elif budget_max is not None:
            orig = f"up to {budget_max} {currency}"
            budget_str = orig + (f" (≈ ${usd_max})" if usd_max is not None else "")
    lines = [f"<b>{title}</b>"]
    if budget_str:
        lines.append(f"💰 <i>{budget_str}</i>")
    if desc:
        lines.append(desc)
    mk = it.get("matched_keyword") or it.get("match") or it.get("keyword")
    if mk:
        lines.append(f"🔎 <i>Match: {mk}</i>")
    lines.append(f"🏷️ <i>{src}</i>")
    return "
".join(lines)

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

def _build_keyboard(links: Dict[str, Optional[str]]):
    if _job_kb is not None:
        try:
            return _job_kb(links["original"], links["proposal"], links["affiliate"])
        except TypeError:
            try:
                return _job_kb(links)
            except Exception:
                pass
    row1 = [
        InlineKeyboardButton("📝 Proposal", url=links["proposal"] or links["original"] or ""),
        InlineKeyboardButton("🔗 Original", url=links["original"] or ""),
    ]
    row2 = [
        InlineKeyboardButton("⭐ Save", callback_data="job:save"),
        InlineKeyboardButton("🗑️ Delete", callback_data="job:delete"),
    ]
    return InlineKeyboardMarkup([row1, row2])

# ---------- users ----------
def _fetch_all_users() -> List[int]:

def _fetch_user_keywords(user_id: int) -> list:
    try:
        return [k for k in (_list_keywords(user_id) or []) if k and k.strip()]
    except Exception:
        return []
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
        kb = _build_keyboard(links)
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
                disable_web_page_preview=False
            )
            _mark_sent(chat_id, k)
            sent += 1
            await asyncio.sleep(0.35)
        except Exception as e:
            log.warning("send_message failed for %s: %s", chat_id, e)

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
            users = await asyncio.to_thread(_fetch_all_users)
            if users:
                for uid in users:
                    kws = await asyncio.to_thread(_fetch_user_keywords, uid)
                    items = await asyncio.to_thread(_worker.run_pipeline, kws)
                    if items:
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
