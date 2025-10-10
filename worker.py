# worker.py — periodic fetch, keyword match, USD conversion, time-ago, save-ready callback data
from __future__ import annotations
import asyncio, json, os
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Tuple

import logging
from sqlalchemy import text

from db import get_session
from db_events import ensure_feed_events_schema, upsert_events
from fetchers import ALL_FETCHERS
from config import FETCH_INTERVAL_SEC, BOT_TOKEN, DELIVERY_WINDOW_HOURS

# PTB Bot (standalone όταν δεν υπάρχει Application)
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

log = logging.getLogger("worker")
logging.basicConfig(level=logging.INFO)

# ---------------- FX (EUR/GBP/... -> USD) ----------------
DEFAULT_RATES = {
    "USD": 1.0,
    "EUR": 1.07,
    "GBP": 1.24,
    "AUD": 0.65,
    "CAD": 0.73,
    "INR": 0.012,
    "BRL": 0.18,
    "TRY": 0.031,
}
def fx_rates() -> Dict[str, float]:
    raw = os.getenv("FX_RATES_JSON", "")
    if not raw:
        return DEFAULT_RATES
    try:
        data = json.loads(raw)
        # καθάρισε κλειδιά σε upper
        return {k.upper(): float(v) for k, v in data.items()}
    except Exception:
        return DEFAULT_RATES

def to_usd(amount: float | None, currency: str | None) -> tuple[str, bool]:
    """returns (text, converted_ok)."""
    if amount is None or not currency:
        return ("", False)
    c = currency.upper().strip()
    rate = fx_rates().get(c)
    if rate is None:
        return (f"{amount:g} {c}", False)
    usd = round(amount * rate, 2)
    return (f"{usd:g} USD", True)

# ---------------- helpers ----------------
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

def _short(desc: str, n: int = 140) -> str:
    d = (desc or "").strip().replace("\n", " ")
    return d if len(d) <= n else (d[: n - 1].rstrip() + "…")

def _time_ago(dt: datetime | None) -> str:
    if not isinstance(dt, datetime):
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    s = int(delta.total_seconds())
    if s < 60:   return f"{s}s ago"
    m = s // 60
    if m < 60:   return f"{m}m ago"
    h = m // 60
    if h < 24:   return f"{h}h ago"
    d = h // 24
    return f"{d}d ago"

async def _send_job_card(tg_bot: Bot, chat_id: int, ev: Dict[str, Any], matched: List[str]) -> None:
    """Κάρτα «φωτογραφία 4»: Budget σε USD, time-ago, περιγραφή, Proposal/Original + Save/Delete."""
    title = ev.get("title") or "(no title)"
    platform = ev.get("platform") or "Freelancer"
    aff = ev.get("affiliate_url")
    url = aff or ev.get("original_url")
    budget = ev.get("budget_amount")
    bcur = ev.get("budget_currency")
    created = ev.get("created_at")

    # Budget → USD
    budget_str, ok = to_usd(budget, bcur)
    budget_line = f"<b>Budget:</b> {budget_str}\n" if budget_str else ""

    matched_line = ", ".join(matched) if matched else ""
    desc_line = _short(ev.get("description", ""))
    ago = _time_ago(created)
    ago_line = f"\n<i>{ago}</i>" if ago else ""

    txt = (
        f"<b>{title}</b>\n"
        f"{budget_line}"
        f"<b>Source:</b> {platform}\n"
        f"<b>Match:</b> {matched_line}\n"
        f"✏️ {desc_line}{ago_line}"
    ).strip()

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Proposal", url=url),
         InlineKeyboardButton("🔗 Original", url=url)],
        [InlineKeyboardButton(f"⭐ Save", callback_data=f"job:save:{ev['id']}"),
         InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")],
    ])

    await tg_bot.send_message(
        chat_id=chat_id, text=txt, parse_mode="HTML",
        reply_markup=kb, disable_web_page_preview=True
    )

def _get_bot(app) -> Bot:
    if app is not None and getattr(app, "bot", None) is not None:
        return app.bot  # type: ignore[return-value]
    return Bot(BOT_TOKEN)

async def run_once(app=None) -> int:
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

    # 4) Pull πρόσφατα events με id & created_at
    since = datetime.now(timezone.utc) - timedelta(hours=DELIVERY_WINDOW_HOURS)
    with get_session() as s:
        rows = s.execute(text("""
            SELECT id, platform, title, description, original_url, affiliate_url,
                   country, budget_amount, budget_currency, created_at
            FROM job_event
            WHERE created_at >= :since
            ORDER BY created_at DESC
        """), {"since": since}).fetchall()

    fresh_events: List[Dict[str, Any]] = []
    for r in rows:
        fresh_events.append({
            "id": r[0],
            "platform": r[1],
            "title": r[2],
            "description": r[3] or "",
            "original_url": r[4],
            "affiliate_url": r[5],
            "country": r[6],
            "budget_amount": r[7],
            "budget_currency": r[8],
            "created_at": r[9],
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
