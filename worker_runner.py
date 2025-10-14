#!/usr/bin/env python3
# worker_runner.py — per-user fetch, force keyword match display, DB dedup, correct budget formatting

import os, logging, asyncio, hashlib
from typing import Dict, List, Optional, Set

import worker as _worker
from sqlalchemy import text as _sql_text
from db import get_session as _get_session
from db_keywords import list_keywords as _list_keywords

from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
log = logging.getLogger("worker")

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
        except Exception as e:
            log.info("[users] skip 'user': %s", e)
        try:
            rows = s.execute(_sql_text("""
                SELECT DISTINCT telegram_id
                FROM users
                WHERE telegram_id IS NOT NULL
                  AND COALESCE(is_blocked,false)=false
            """)).fetchall()
            ids.update(int(r[0]) for r in rows if r[0] is not None)
        except Exception as e:
            log.info("[users] skip 'users': %s", e)
    out = sorted(list(ids))
    log.info("[users] receivers: %s", len(out))
    return out

def _fetch_user_keywords(user_id: int) -> List[str]:
    try:
        return [k for k in (_list_keywords(user_id) or []) if k and k.strip()]
    except Exception:
        return []

def _find_match_keyword(it: Dict, kws: List[str]) -> Optional[str]:
    """Return the ORIGINAL keyword (exact casing as stored) that matches item (case-insensitive)."""
    if not kws:
        return None
    title = (it.get("title") or "").lower()
    desc = (it.get("description") or "").lower()
    hay = f"{title}\n{desc}"
    for kw in kws:
        k = (kw or "").strip()
        if not k:
            continue
        if k.lower() in hay:
            return k  # return as originally stored
    return None

# ============ Message compose ============
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
    # Αν έχεις custom ui_keyboards.job_action_kb θα χρησιμοποιηθεί· αλλιώς default
    try:
        from ui_keyboards import job_action_kb as _job_kb
        return _job_kb(links["original"], links["proposal"], links["affiliate"])
    except Exception:
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

# ============ Send (DB dedup) ============
async def _send_items(bot: Bot, chat_id: int, items: List[Dict], per_user_batch: int):
    sent = 0
    for it in items:
        if sent >= per_user_batch:
            break

        # Σταθερό κλειδί: προτιμά URL, αλλιώς source+title
        base_key = f"{it.get('url') or it.get('original_url') or ''}"
        if not base_key:
            base_key = f"{it.get('source','')}::{it.get('title','')[:160]}"
        job_key = hashlib.sha1(base_key.encode("utf-8", "ignore")).hexdigest()

        if _already_sent(chat_id, job_key):
            continue

        try:
            text = _compose_message(it)
            kb = _build_keyboard(_resolve_links(it))
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
                disable_web_page_preview=False
            )
            _mark_sent(chat_id, job_key)
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

    while True:
        try:
            users = await asyncio.to_thread(_fetch_all_users)
            if users:
                for uid in users:
                    kws = await asyncio.to_thread(_fetch_user_keywords, uid)
                    items = await asyncio.to_thread(_worker.run_pipeline, kws)

                    # 🔎 Εγγυημένα βάζουμε το matched_keyword (όπως το έχει γράψει ο χρήστης)
                    for it in items:
                        if not it.get("matched_keyword"):
                            mk = _find_match_keyword(it, kws)
                            if mk:
                                it["matched_keyword"] = mk

                    if items:
                        await _send_items(bot, uid, items, per_user_batch)
        except Exception as e:
            log.error("[runner] pipeline error: %s", e)

        await asyncio.sleep(interval)

if __name__ == "__main__":
    asyncio.run(amain())
