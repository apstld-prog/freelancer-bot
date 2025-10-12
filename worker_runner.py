#!/usr/bin/env python3
# worker_runner.py — runner + send loop to ALL users (keeps UI identical)
# Env:
#   TELEGRAM_BOT_TOKEN (required)
#   WORKER_INTERVAL=60 (optional)
#   WORKER_CLEANUP_DAYS=7 (optional; run once on start if >0)
#   BATCH_PER_TICK=5 (optional; how many items per user per tick)

import os
import time
import logging
from typing import Dict, List, Optional, Iterable, Set

import worker as _worker
from sqlalchemy import text as _sql_text
from db import get_session as _get_session

# Prefer the existing keyboard builder (exact same UI)
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

def _compose_message(it: Dict) -> str:
    title = (it.get("title") or "").strip() or "Untitled"
    desc = (it.get("description") or "").strip()
    if len(desc) > 700:
        desc = desc[:700] + "…"
    src = it.get("source", "freelancer")
    budget_min = it.get("budget_min")
    budget_max = it.get("budget_max")
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
    # ensure freelancer affiliate link if missing
    if (it.get("source") or "").lower() == "freelancer" and original and not affiliate:
        try:
            affiliate = _worker.wrap_freelancer(original)
        except Exception:
            pass
    return {"original": original, "proposal": proposal, "affiliate": affiliate}

def _build_keyboard(links: Dict[str, Optional[str]]):
    if _job_kb is not None:
        # try common signatures used in the project
        try:
            return _job_kb(links["original"], links["proposal"], links["affiliate"])
        except TypeError:
            try:
                return _job_kb(links)
            except Exception:
                pass
    # fallback (same labels as UI)
    row1 = [
        InlineKeyboardButton("📝 Proposal", url=links["proposal"] or links["original"] or ""),
        InlineKeyboardButton("🔗 Original", url=links["original"] or ""),
    ]
    row2 = [
        InlineKeyboardButton("⭐ Save", callback_data="job:save"),
        InlineKeyboardButton("🗑️ Delete", callback_data="job:delete"),
    ]
    return InlineKeyboardMarkup([row1, row2])

def _send_items(bot: Bot, chat_id: int, items: List[Dict], per_user_batch: int):
    for it in items[:per_user_batch]:
        text = _compose_message(it)
        links = _resolve_links(it)
        kb = _build_keyboard(links)
        try:
            bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
                disable_web_page_preview=False
            )
            time.sleep(0.4)  # be gentle
        except Exception as e:
            log.warning("send_message failed for %s: %s", chat_id, e)

def _fetch_all_users() -> List[int]:
    """
    Collect DISTINCT telegram_id from both 'user' and 'users' tables.
    - ignore NULL
    - if 'is_blocked' exists, filter it out
    - if 'is_active' exists, prefer active only
    """
    ids: Set[int] = set()
    with _get_session() as s:
        # table: user
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
            log.info("[users] skip 'user' table: %s", e)

        # table: users
        try:
            rows = s.execute(_sql_text("""
                SELECT DISTINCT telegram_id
                FROM users
                WHERE telegram_id IS NOT NULL
                  AND (COALESCE(is_blocked, false) = false)
            """)).fetchall()
            ids.update(int(r[0]) for r in rows if r[0] is not None)
        except Exception as e:
            log.info("[users] skip 'users' table: %s", e)

    out = sorted(list(ids))
    log.info("[users] total distinct receivers: %s", len(out))
    return out

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")

    interval = _get_env_int("WORKER_INTERVAL", 60)
    per_user_batch = _get_env_int("BATCH_PER_TICK", 5)

    # optional cleanup 1x on start
    cleanup_days_raw = os.getenv("WORKER_CLEANUP_DAYS", "")
    if cleanup_days_raw and cleanup_days_raw.lower() not in ("0", "false"):
        try:
            d = int(cleanup_days_raw)
            log.info("[cleanup] using make_interval days=%s", d)
            _worker._cleanup_old_sent_jobs(d)
            log.info("[Runner] cleanup executed on start (days=%s)", d)
        except Exception as e:
            log.warning("[Runner] cleanup failed: %s", e)

    bot = Bot(token=token)

    while True:
        try:
            # 1) get content
            items = _worker.run_pipeline([])  # KEYWORD_FILTER_MODE=off => no filters
            if not items:
                log.info("[pipeline] no items this tick")
            # 2) get all receivers
            users = _fetch_all_users()
            # 3) send per user (small batch)
            if items and users:
                for uid in users:
                    _send_items(bot, uid, items, per_user_batch)
        except Exception as e:
            log.error("[runner] pipeline/send error: %s", e)

        time.sleep(interval)

if __name__ == "__main__":
    main()
