#!/usr/bin/env python3
# worker_runner.py — stable version with correct Match, dedup, and currency formatting

import os, logging, asyncio
from typing import Dict, List, Optional, Set
import hashlib

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

# ---------- Users ----------
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

def _fetch_user_keywords(user_id: int) -> List[str]:
    try:
        return [k for k in (_list_keywords(user_id) or []) if k and k.strip()]
    except Exception:
        return []

# ---------- Message Compose ----------
def _compose_message(it: Dict) -> str:
    title = (it.get("title") or "").strip() or "Untitled"
    desc = (it.get("description") or "").strip()
    if len(desc) > 700:
        desc = desc[:700] + "…"
    src = it.get("source", "freelancer")

    display_ccy = (
        it.get("currency_display")
        or it.get("budget_currency")
        or it.get("original_currency")
        or it.get("currency_code_detected")
        or it.get("currency")
        or "USD"
    )

    budget_min, budget_max = it.get("budget_min"), it.get("budget_max")
    usd_min, usd_max = it.get("budget_min_usd"), it.get("budget_max_usd")

    def _fmt(v):
        try:
            f = float(v)
            s = f"{f:.1f}"
            return s.rstrip("0").rstrip(".")
        except Exception:
            return str(v)

    budget_str = ""
    if budget_min is not None and budget_max is not None:
        orig = f"{_fmt(budget_min)}–{_fmt(budget_max)} {display_ccy}".strip()
        if usd_min is not None and usd_max is not None:
            budget_str = f"{orig} (≈ ${_fmt(usd_min)}–${_fmt(usd_max)})"
        else:
            budget_str = orig
    elif budget_min is not None:
        orig = f"from {_fmt(budget_min)} {display_ccy}".strip()
        budget_str = orig + (f" (≈ ${_fmt(usd_min)})" if usd_min is not None else "")
    elif budget_max is not None:
        orig = f"up to {_fmt(budget_max)} {display_ccy}".strip()
        budget_str = orig + (f" (≈ ${_fmt(usd_max)})" if usd_max is not None else "")

    lines = [f"<b>{title}</b>"]
    if budget_str:
        lines.append(f"💰 <i>{budget_str}</i>")
    if desc:
        lines.append(desc)

    mk = it.get("matched_keyword") or it.get("match") or it.get("keyword")
    if mk:
        lines.append(f"🔎 <i>Match: {mk}</i>")

    lines.append(f"🏷️ <i>{src}</i>")
    return "\n".join(lines)

def _build_keyboard(links: Dict[str, Optional[str]]):
    if _job_kb is not None:
        try:
            return _job_kb(links["original"], links["proposal"], links["affiliate"])
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

# ---------- Send with simple dedup ----------
_sent_cache = set()

async def _send_items(bot: Bot, chat_id: int, items: List[Dict], per_user_batch: int):
    sent = 0
    for it in items:
        if sent >= per_user_batch:
            break

        # lightweight dedup (same title+url hash)
        key = f"{it.get('source','')}::{it.get('title','')[:80]}::{it.get('url') or it.get('original_url') or ''}"
        key_hash = hashlib.sha1(key.encode()).hexdigest()
        cache_key = f"{chat_id}:{key_hash}"
        if cache_key in _sent_cache:
            continue
        _sent_cache.add(cache_key)

        try:
            text = _compose_message(it)
            kb = _build_keyboard(_resolve_links(it))
            await bot.send_message(chat_id=chat_id, text=text,
                                   parse_mode=ParseMode.HTML,
                                   reply_markup=kb, disable_web_page_preview=False)
            sent += 1
            await asyncio.sleep(0.35)
        except Exception as e:
            log.warning("send_message failed for %s: %s", chat_id, e)

# ---------- Main loop ----------
async def amain():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")
    interval = int(os.getenv("WORKER_INTERVAL", "120"))
    per_user_batch = int(os.getenv("BATCH_PER_TICK", "5"))
    bot = Bot(token=token)

    while True:
        try:
            users = await asyncio.to_thread(_fetch_all_users)
            for uid in users:
                kws = await asyncio.to_thread(_fetch_user_keywords, uid)
                items = await asyncio.to_thread(_worker.run_pipeline, kws)
                # ✅ Ensure match keyword always appears
                for it in items:
                    mk = _worker.match_keywords(it, kws)
                    if mk:
                        it["matched_keyword"] = mk
                if items:
                    await _send_items(bot, uid, items, per_user_batch)
        except Exception as e:
            log.error("[runner] error: %s", e)
        await asyncio.sleep(interval)

if __name__ == "__main__":
    asyncio.run(amain())
