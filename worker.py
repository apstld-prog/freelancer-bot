# worker.py — periodic fetch, keyword match, dedup, affiliate-preferred
from __future__ import annotations
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Tuple

import logging
from sqlalchemy import text

from db import get_session
from db_events import ensure_feed_events_schema, upsert_events
from fetchers import ALL_FETCHERS
from config import FETCH_INTERVAL_SEC, BOT_TOKEN, DELIVERY_WINDOW_HOURS

# PTB Bot (standalone when no Application provided)
from telegram import Bot

log = logging.getLogger("worker")
logging.basicConfig(level=logging.INFO)

def _load_all_user_keywords() -> List[Tuple[int, int, List[str]]]:
    """Return list of (user_id, telegram_id, keywords_lower[])."""
    with get_session() as s:
        rows = s.execute(text('SELECT id, telegram_id FROM "user" WHERE is_active=TRUE AND is_blocked=FALSE')).fetchall()
        out: List[Tuple[int, int, List[str]]] = []
        for uid, tid in rows:
            kws = s.execute(text("""
                SELECT COALESCE(keyword, value) AS k FROM keyword WHERE user_id=:uid ORDER BY id
            """), {"uid": uid}).fetchall()
            out.append((int(uid), int(tid), [x[0].lower() for x in kws if x and x[0]]))
        return out

def _match_keywords(title: str, description: str, kws: List[str]) -> List[str]:
    hay = f"{title}\n{description}".lower()
    return [k for k in kws if k in hay]

async def _send_job_card(tg_bot, chat_id: int, ev: Dict[str, Any], matched: List[str]) -> None:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    title = ev.get("title") or "(no title)"
    platform = ev.get("platform") or "Unknown"
    aff = ev.get("affiliate_url")
    url = aff or ev.get("original_url")
    budget = ev.get("budget_amount")
    bcur = ev.get("budget_currency")
    budget_line = f"<b>Budget:</b> {budget} {bcur}\n" if budget and bcur else ""

    matched_line = ", ".join(matched) if matched else ""
    txt = (
        f"<b>{title}</b>\n"
        f"{budget_line}"
        f"<b>Source:</b> {platform}\n"
        f"<b>Match:</b> {matched_line}\n"
    ).strip()

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Proposal", url=url),
         InlineKeyboardButton("🔗 Original", url=url)],
        [InlineKeyboardButton("⭐ Save", callback_data="job:save"),
         InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")],
    ])

    try:
        await tg_bot.send_message(
            chat_id=chat_id, text=txt, parse_mode="HTML",
            reply_markup=kb, disable_web_page_preview=True
        )
    except Exception as e:
        log.warning("send_message failed: %s", e)

def _get_bot(app) -> Bot:
    if app is not None and getattr(app, "bot", None) is not None:
        return app.bot  # type: ignore[return-value]
    return Bot(BOT_TOKEN)

async def run_once(app=None) -> int:
    """Fetch all sources, upsert, then deliver to matching users across a configurable window."""
    ensure_feed_events_schema()

    # 1) Fetch
    results = await asyncio.gather(*(f() for f in ALL_FETCHERS), return_exceptions=False)
    all_events: List[Dict[str, Any]] = [e for sub in results for e in sub]

    # 2) Upsert
    new_count = upsert_events(all_events) if all_events else 0
    log.info("Upserted events: new=%d total_in_batch=%d", new_count, len(all_events))

    # 3) Users + keywords
    users = _load_all_user_keywords()
    if not users:
        log.info("No active users to notify.")
        return new_count

    # 4) Recent events (wider window so matches δεν χάνονται)
    since = datetime.now(timezone.utc) - timedelta(hours=DELIVERY_WINDOW_HOURS)
    with get_session() as s:
        rows = s.execute(text("""
            SELECT platform, title, description, original_url, affiliate_url, country, budget_amount, budget_currency
            FROM job_event
            WHERE created_at >= :since
            ORDER BY created_at DESC
        """), {"since": since}).fetchall()

    fresh_events: List[Dict[str, Any]] = []
    for r in rows:
        fresh_events.append({
            "platform": r[0],
            "title": r[1],
            "description": r[2] or "",
            "original_url": r[3],
            "affiliate_url": r[4],
            "country": r[5],
            "budget_amount": r[6],
            "budget_currency": r[7],
        })

    # 5) Notify
    tg_bot = _get_bot(app)
    notified = 0
    for uid, tid, kws in users:
        for ev in fresh_events:
            matched = _match_keywords(ev["title"], ev["description"], kws)
            if matched:
                await _send_job_card(tg_bot, tid, ev, matched)
                notified += 1

    log.info("Delivered %d job cards to users.", notified)
    return new_count

async def main(app=None):
    log.info("Worker started (interval=%ss).", FETCH_INTERVAL_SEC)
    while True:
        try:
            await run_once(app)
        except Exception as e:
            log.exception("Worker loop error: %s", e)
        await asyncio.sleep(FETCH_INTERVAL_SEC)

if __name__ == "__main__":
    asyncio.run(main())
