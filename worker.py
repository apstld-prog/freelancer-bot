# worker.py — στείλε λίγα/ελεγχόμενα, σταμάτα run όταν RetryAfter είναι μεγάλο
from __future__ import annotations
import asyncio, os, logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Tuple

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import RetryAfter

from sqlalchemy import text

from db import get_session
from db_events import ensure_feed_events_schema, upsert_events
from fetchers import ALL_FETCHERS
from config import FETCH_INTERVAL_SEC, BOT_TOKEN, DELIVERY_WINDOW_HOURS

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker")

# Anti-flood (ρυθμίζονται και από ENV)
MAX_MSGS_PER_RUN = int(os.getenv("MAX_MSGS_PER_RUN", "8"))      # μικρό batch
MSG_DELAY_MS     = int(os.getenv("MSG_DELAY_MS", "500"))        # 0.5s ανά μήνυμα
RETRY_AFTER_CAP  = int(os.getenv("RETRY_AFTER_CAP", "30"))      # αν >30s, σταμάτα run

def _short(s: str, n: int = 160) -> str:
    s = (s or "").strip().replace("\n", " ")
    return s if len(s) <= n else (s[: n - 1].rstrip() + "…")

def _time_ago(dt: datetime | None) -> str:
    if not isinstance(dt, datetime): return ""
    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
    sec = int((datetime.now(timezone.utc) - dt).total_seconds())
    if sec < 60: return f"{sec}s ago"
    m = sec // 60
    if m < 60: return f"{m}m ago"
    h = m // 60
    if h < 24: return f"{h}h ago"
    d = h // 24
    return f"{d}d ago"

async def _send(bot: Bot, chat_id: int, text: str, kb: InlineKeyboardMarkup):
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML",
                               reply_markup=kb, disable_web_page_preview=True)
    except RetryAfter as e:
        if int(getattr(e, "retry_after", 0)) > RETRY_AFTER_CAP:
            # σταμάτα το run – ας ξαναδοκιμάσουμε στον επόμενο κύκλο
            raise
        await asyncio.sleep(max(1, int(e.retry_after)))
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML",
                               reply_markup=kb, disable_web_page_preview=True)

async def _send_card(bot: Bot, tid: int, ev: Dict[str, Any], matched: List[str]):
    title = ev.get("title") or "(no title)"
    platform = ev.get("platform") or "Freelancer"
    desc = _short(ev.get("description",""))
    ago = _time_ago(ev.get("created_at"))
    budget_amount = ev.get("budget_amount")
    budget_currency = ev.get("budget_currency")
    budget_line = f"<b>Budget:</b> {budget_amount:g} {budget_currency}\n" if (budget_amount and budget_currency) else ""

    txt = (
        f"<b>{title}</b>\n"
        f"{budget_line}"
        f"<b>Source:</b> {platform}\n"
        f"<b>Match:</b> {', '.join(matched)}\n"
        f"✏️ {desc}\n<i>{ago}</i>"
    ).strip()
    url = ev.get("affiliate_url") or ev.get("original_url") or "#"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Proposal", url=url),
         InlineKeyboardButton("🔗 Original", url=url)],
        [InlineKeyboardButton("⭐ Save", callback_data=f"job:save:{ev['id']}"),
         InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")]
    ])
    await _send(bot, tid, txt, kb)

def _load_users() -> List[Tuple[int, int, List[str]]]:
    with get_session() as s:
        users = s.execute(text('SELECT id, telegram_id FROM "user" WHERE is_active=TRUE AND is_blocked=FALSE')).fetchall()
        out = []
        for uid, tid in users:
            kws = s.execute(text("SELECT COALESCE(keyword,value) FROM keyword WHERE user_id=:u"), {"u": uid}).fetchall()
            out.append((int(uid), int(tid), [k[0].lower() for k in kws if k and k[0]]))
        return out

def _match(hay_title: str, hay_desc: str, kws: List[str]) -> List[str]:
    hay = f"{hay_title}\n{hay_desc}".lower()
    return [k for k in kws if k in hay]

async def run_once(app=None) -> int:
    ensure_feed_events_schema()

    # fetch
    res = await asyncio.gather(*(f() for f in ALL_FETCHERS), return_exceptions=False)
    events = [e for sub in res for e in sub]
    newc = upsert_events(events) if events else 0
    log.info("Upserted events: new=%d total_in_batch=%d", newc, len(events))

    users = _load_users()
    if not users: return newc

    since = datetime.now(timezone.utc) - timedelta(hours=DELIVERY_WINDOW_HOURS)
    with get_session() as s:
        rows = s.execute(text("""
            SELECT id, platform, title, description, original_url, affiliate_url,
                   budget_amount, budget_currency, created_at
            FROM job_event
            WHERE created_at >= :since
            ORDER BY created_at DESC
        """), {"since": since}).fetchall()

    evs = [{
        "id": r[0], "platform": r[1], "title": r[2], "description": r[3] or "",
        "original_url": r[4], "affiliate_url": r[5],
        "budget_amount": r[6], "budget_currency": r[7], "created_at": r[8],
    } for r in rows]

    bot = Bot(BOT_TOKEN)

    sent = 0
    try:
        for uid, tid, kws in users:
            for ev in evs:
                if sent >= MAX_MSGS_PER_RUN: break
                m = _match(ev["title"], ev["description"], kws)
                if m:
                    await _send_card(bot, tid, ev, m)
                    sent += 1
                    await asyncio.sleep(MSG_DELAY_MS / 1000.0)
            if sent >= MAX_MSGS_PER_RUN: break
        log.info("Delivered %d cards (rate-limited).", sent)
    except RetryAfter as e:
        log.warning("Flood control: RetryAfter=%ss — stop this run", int(e.retry_after))
    return newc

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
