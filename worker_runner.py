#!/usr/bin/env python3
# worker_runner.py — async runner: send-to-all + per-user dedup (PTB v20+)
# Env:
#   TELEGRAM_BOT_TOKEN (required)
#   WORKER_INTERVAL=60 (optional)
#   WORKER_CLEANUP_DAYS=7 (optional)
#   BATCH_PER_TICK=5 (optional)

import os, time, logging, asyncio
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
    try: return int(str(os.getenv(name, default)).strip())
    except Exception: return default

# ---------- sent_job schema + helpers (sync SQL) ----------
def _ensure_sent_schema():
    with _get_session() as s:
        s.execute(_sql_text("""
            CREATE TABLE IF NOT EXISTS sent_job (
                user_id BIGINT NOT NULL,
                job_key TEXT NOT NULL,
                sent_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
                PRIMARY KEY (user_id, job_key)
            );
        """))
        s.commit()
    log.info("[dedup] sent_job schema ensured")

def _already_sent(user_id: int, job_key: str) -> bool:
    with _get_session() as s:
        row = s.execute(
            _sql_text("SELECT 1 FROM sent_job WHERE user_id=:u AND job_key=:k LIMIT 1;"),
            {"u": user_id, "k": job_key},
        ).fetchone()
        return row is not None

def _mark_sent(user_id: int, job_key: str):
    with _get_session() as s:
        s.execute(
            _sql_text("""
                INSERT INTO sent_job (user_id, job_key)
                VALUES (:u, :k)
                ON CONFLICT (user_id, job_key) DO NOTHING;
            """),
            {"u": user_id, "k": job_key},
        )
        s.commit()

# ---------- compose + keyboard ----------
def _compose_message(it: Dict) -> str:
    title = (it.get("title") or "").strip() or "Untitled"
    desc = (it.get("description") or "").strip()
    if len(desc) > 700: desc = desc[:700] + "…"
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
    if budget_str: lines.append(f"💰 <i>{budget_str}</i>")
    if desc: lines.append(desc)
    lines.append(f"🏷️ <i>{src}</i>")
    return "\n".join(lines)

def _resolve_links(it: Dict) -> Dict[str, Optional[str]]:
    original = it.get("original_url") or it.get("url") or ""
    proposal = it.get("proposal_url") or original or ""
    affiliate = it.get("affiliate_url") or ""
    if (it.get("source") or "").lower() == "freelancer" and original and not affiliate:
        try: affiliate = _worker.wrap_freelancer(original)
        except Exception: pass
    return {"original": original, "proposal": proposal, "affiliate": affiliate}

def _build_keyboard(links: Dict[str, Optional[str]]):
    if _job_kb is not None:
        try: return _job_kb(links["original"], links["proposal"], links["affiliate"])
        except TypeError:
            try: return _job_kb(links)
            except Exception: pass
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
        try: return _make_key(it)
        except Exception: pass
    sid = str(it.get("id") or it.get("original_url") or it.get("url") or it.get("title") or "")[:512]
    return f"{it.get('source','unknown')}::{sid}"

# ---------- async send ----------
async def _send_items(bot: Bot, chat_id: int, items: List[Dict], per_user_batch: int):
    sent = 0
    for it in items:
        if sent >= per_user_batch: break
        k = _job_key(it)
        if _already_sent(chat_id, k): continue
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
            # τρέξε sync pipeline σε ξεχωριστό thread για να μην μπλοκάρει event loop
            items = await asyncio.to_thread(_worker.run_pipeline, [])
            users = await asyncio.to_thread(_fetch_all_users)
            if items and users:
                for uid in users:
                    await _send_items(bot, uid, items, per_user_batch)
            else:
                if not items: log.info("[pipeline] no items this tick")
                if not users: log.info("[users] no receivers")
        except Exception as e:
            log.error("[runner] pipeline/send error: %s", e)

        await asyncio.sleep(interval)

if __name__ == "__main__":
    asyncio.run(amain())
