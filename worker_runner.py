#!/usr/bin/env python3
# worker_runner.py — async runner: send-to-all + per-user dedup (PTB v20+)
# Robust dedup schema: supports sent_job.{user_id|chat_id}
# Env:
#   TELEGRAM_BOT_TOKEN (required)
#   WORKER_INTERVAL=60 (optional)
#   WORKER_CLEANUP_DAYS=7 (optional)
#   BATCH_PER_TICK=5 (optional)

import os, logging, asyncio
from typing import Dict, List, Optional, Set

import worker as _worker
from sqlalchemy import text as _sql_text
from db import get_session as _get_session

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

# ---------- sent_job schema + helpers (per-user dedup, robust) ----------
def _sent_user_col() -> str:
    """
    Detect which id column exists for sent_job: prefer user_id, else chat_id.
    If table doesn't exist or has none, default to 'user_id' (the creator will add it).
    """
    with _get_session() as s:
        row = s.execute(_sql_text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'sent_job'
              AND column_name IN ('user_id','chat_id')
            ORDER BY CASE WHEN column_name='user_id' THEN 0 ELSE 1 END
            LIMIT 1
        """)).fetchone()
        if row:
            return row[0]
    return "user_id"

def _ensure_sent_schema():
    """
    Create/normalize sent_job so that it has (idcol, job_key, sent_at) and a PK on (idcol, job_key).
    - If the table exists with chat_id only, we keep chat_id.
    - If the table doesn't have any id column, we add user_id.
    """
    with _get_session() as s:
        # Ensure table exists
        s.execute(_sql_text("""
            CREATE TABLE IF NOT EXISTS sent_job (
                user_id BIGINT,
                job_key TEXT,
                sent_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
            );
        """))

        # Determine id column (prefer existing user_id/chat_id)
        row = s.execute(_sql_text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='sent_job' AND column_name IN ('user_id','chat_id')
            ORDER BY CASE WHEN column_name='user_id' THEN 0 ELSE 1 END
            LIMIT 1
        """)).fetchone()

        if row:
            idcol = row[0]
        else:
            # No id column at all → add user_id
            s.execute(_sql_text("ALTER TABLE sent_job ADD COLUMN user_id BIGINT;"))
            idcol = "user_id"

        # Ensure job_key exists
        has_job_key = s.execute(_sql_text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name='sent_job' AND column_name='job_key' LIMIT 1
        """)).fetchone()
        if not has_job_key:
            s.execute(_sql_text("ALTER TABLE sent_job ADD COLUMN job_key TEXT;"))

        # Recreate PK on (idcol, job_key)
        s.execute(_sql_text("""
            DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname='sent_job_pkey') THEN
                    ALTER TABLE sent_job DROP CONSTRAINT sent_job_pkey;
                END IF;
            END $$;
        """))
        s.execute(_sql_text(f"ALTER TABLE sent_job ADD CONSTRAINT sent_job_pkey PRIMARY KEY ({idcol}, job_key);"))
        s.commit()
    log.info("[dedup] sent_job schema ensured (id column: %s)", _sent_user_col())

def _already_sent(user_id: int, job_key: str) -> bool:
    idcol = _sent_user_col()
    with _get_session() as s:
        row = s.execute(
            _sql_text(f"SELECT 1 FROM sent_job WHERE {idcol}=:u AND job_key=:k LIMIT 1;"),
            {"u": user_id, "k": job_key},
        ).fetchone()
        return row is not None

def _mark_sent(user_id: int, job_key: str):
    idcol = _sent_user_col()
    with _get_session() as s:
        s.execute(
            _sql_text(f"""
                INSERT INTO sent_job ({idcol}, job_key)
                VALUES (:u, :k)
                ON CONFLICT ({idcol}, job_key) DO NOTHING;
            """),
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
    currency = it.get("currency") or ""
    budget_str = ""
    if budget_min is not None or budget_max is not None:
        if budget_min is not None and budget_max is not None:
            budget_str = f"{budget_min}–{budget_max} {currency}"
        elif budget_min is not None:
            budget_str = f"from {budget_min} {currency}"
        elif budget_max is not None:
            budget_str = f"up to {budget_max} {currency}"
    lines = [f"<b>{title}</b>"]
    if budget_str:
        lines.append(f"💰 <i>{budget_str}</i>")
    if desc:
        lines.append(desc)
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
