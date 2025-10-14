#!/usr/bin/env python3
# worker_runner.py — async runner: send-to-all + per-user dedup + keyword match + currency fix

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


# ---------- user keywords ----------
def _fetch_user_keywords(user_id: int) -> list:
    try:
        return [k for k in (_list_keywords(user_id) or []) if k and k.strip()]
    except Exception:
        return []


# ---------- message composer ----------
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
    return "\n".join(lines)


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


# ---------- async send ----------
async def _send_items(bot: Bot, chat_id: int, items: List[Dict], per_user_batch: int):
    sent = 0
    for it in items:
        if sent >= per_user_batch:
            break
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
            sent += 1
            await asyncio.sleep(0.35)
        except Exception as e:
            log.warning("send_message failed for %s: %s", chat_id, e)


# ---------- main loop ----------
async def amain():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")

    interval = int(os.getenv("WORKER_INTERVAL", "120"))
    per_user_batch = int(os.getenv("BATCH_PER_TICK", "5"))
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
        except Exception as e:
            log.error("[runner] pipeline/send error: %s", e)

        await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(amain())
