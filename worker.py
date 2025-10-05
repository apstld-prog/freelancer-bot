# worker.py
import os
import re
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote_plus  # <-- for URL quoting

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from db import (
    SessionLocal,
    ensure_schema,
    User,
    JobSent,
)

# ───────────────────────── Logging ─────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [db] %(levelname)s: %(message)s")
log = logging.getLogger("worker")

# ───────────────────────── Env ─────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Search cadence
INTERVAL_SECS = int(os.getenv("WORKER_INTERVAL_SECS", "300"))

# Matching behavior
JOB_MATCH_SCOPE = os.getenv("JOB_MATCH_SCOPE", "title_desc")  # title | title_desc
JOB_MATCH_REQUIRE = os.getenv("JOB_MATCH_REQUIRE", "any")     # any | all

# Freelancer affiliate code (optional)
FREELANCER_REF_CODE = os.getenv("FREELANCER_REF_CODE", "").strip()

# HTTP
HTTP_TIMEOUT = 20.0
HEADERS_HTML = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) FreelancerAlertsBot/1.0"
}

# Currency approx conversion to USD
DEFAULT_USD_RATES = {
    "USD": 1.0, "EUR": 1.07, "GBP": 1.25, "AUD": 0.65, "CAD": 0.73, "CHF": 1.10,
    "SEK": 0.09, "NOK": 0.09, "DKK": 0.14, "PLN": 0.25, "RON": 0.22, "BGN": 0.55,
    "TRY": 0.03, "MXN": 0.055, "BRL": 0.19, "INR": 0.012,
}
def load_usd_rates() -> Dict[str, float]:
    raw = os.getenv("FX_USD_RATES", "").strip()
    if not raw:
        return DEFAULT_USD_RATES
    try:
        data = json.loads(raw)
        safe = {k.upper(): float(v) for k, v in data.items()}
        safe["USD"] = 1.0
        return {**DEFAULT_USD_RATES, **safe}
    except Exception:
        return DEFAULT_USD_RATES
USD_RATES = load_usd_rates()

CURRENCY_SYMBOLS = {
    "USD": "$", "EUR": "€", "GBP": "£",
    "AUD": "A$", "CAD": "C$", "CHF": "CHF",
    "SEK": "SEK", "NOK": "NOK", "DKK": "DKK",
    "PLN": "zł", "RON": "lei", "BGN": "лв",
    "TRY": "₺", "MXN": "MX$", "BRL": "R$", "INR": "₹",
}

UTC = timezone.utc
def now_utc() -> datetime:
    return datetime.now(UTC)

def to_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)

# ───────────────────────── Telegram client (minimal) ─────────────────────────
import asyncio
from telegram import Bot
bot: Optional[Bot] = None

async def get_bot() -> Bot:
    global bot
    if bot is None:
        bot = Bot(BOT_TOKEN)
    return bot

# ───────────────────────── Formatting helpers ─────────────────────────
def fmt_local_budget(minb: float, maxb: float, code: Optional[str]) -> str:
    if not minb and not maxb:
        return "—"
    code_up = (code or "").upper()
    sym = CURRENCY_SYMBOLS.get(code_up, code_up or "")
    if sym:
        return f"{minb:.0f}–{maxb:.0f} {sym}"
    return f"{minb:.0f}–{maxb:.0f} {code_up}"

def to_usd(minb: float, maxb: float, code: Optional[str]) -> Optional[Tuple[float, float]]:
    c = (code or "USD").upper()
    rate = USD_RATES.get(c)
    if not rate:
        return None
    return minb * rate, maxb * rate

def fmt_usd_line(min_usd: float, max_usd: float) -> str:
    return f"~ ${min_usd:.0f}–${max_usd:.0f} USD"

def job_text(card: Dict) -> str:
    lines = [f"*{card.get('title','Untitled')}*",
             "",
             f"👤 Source: *{card.get('source','')}*"]
    if card.get("type"):
        lines.append(f"🧾 Type: *{card['type']}*")
    if card.get("budget_local"):
        lines.append(f"💰 Budget: *{card['budget_local']}*")
    if card.get("budget_usd"):
        lines.append(f"💵 {card['budget_usd']}")
    if card.get("bids") is not None:
        lines.append(f"📨 Bids: *{card['bids']}*")
    if card.get("posted"):
        lines.append(f"🕒 Posted: *{card['posted']}*")
    if card.get("description"):
        lines += ["", card["description"]]
    if card.get("matched"):
        lines += ["", f"_Matched:_ {', '.join(card['matched'])}"]
    return "\n".join(lines)

def card_markup(card: Dict) -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton("💼 Proposal", url=card["proposal_url"]),
        InlineKeyboardButton("🔗 Original", url=card["original_url"]),
    ],
    [
        InlineKeyboardButton("⭐ Keep", callback_data=f"save:{card['id']}"),
        InlineKeyboardButton("🗑 Delete", callback_data=f"dismiss:{card['id']}"),
    ]]
    return InlineKeyboardMarkup(rows)

# ───────────────────────── Freelancer fetch ─────────────────────────
async def freelancer_search(keyword: str) -> List[Dict]:
    url = (
        "https://www.freelancer.com/api/projects/0.1/projects/active/"
        f"?query={quote_plus(keyword)}"
        "&limit=30&compact=true&user_details=true&job_details=true&full_description=true"
    )
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers={"Accept": "application/json"}) as client:
            r = await client.get(url)
            if r.status_code != 200:
                log.warning("Freelancer fetch error for '%s': %s", keyword, r)
                return []
            data = r.json()
    except Exception as e:
        log.warning("Freelancer fetch error for '%s': %s", keyword, e)
        return []

    results = (data or {}).get("result", {}).get("projects", []) or []
    cards: List[Dict] = []
    for p in results:
        pid = str(p.get("id"))
        title = p.get("title") or "Untitled"
        ptype = "Fixed" if p.get("type") == "fixed" else ("Hourly" if p.get("type") == "hourly" else None)
        budget = p.get("budget") or {}
        minb = float(budget.get("minimum") or 0)
        maxb = float(budget.get("maximum") or 0)
        cur = budget.get("currency") or {}
        code = (cur.get("code") or "USD").upper() if isinstance(cur, dict) else "USD"
        local_line = fmt_local_budget(minb, maxb, code)
        usd_pair = to_usd(minb, maxb, code)
        usd_line = fmt_usd_line(*usd_pair) if usd_pair else None

        bids = p.get("bid_stats", {}).get("bid_count", 0)

        base_url = f"https://www.freelancer.com/projects/{pid}"
        sep = "&" if "?" in base_url else "?"
        url_prop = f"{base_url}{sep}f={FREELANCER_REF_CODE}" if FREELANCER_REF_CODE else base_url

        desc = (p.get("description") or "").replace("\r", " ").replace("\n", " ").strip()
        if len(desc) > 220:
            desc = desc[:217] + "…"

        cards.append({
            "id": f"freelancer-{pid}",
            "source": "Freelancer",
            "title": title,
            "type": ptype,
            "budget_local": local_line,
            "budget_usd": usd_line,
            "bids": bids,
            "posted": "recent",
            "description": desc,
            "proposal_url": url_prop,
            "original_url": url_prop,
        })
    log.info("Freelancer '%s': %d jobs", keyword, len(cards))
    return cards

# ───────────────────────── PeoplePerHour fetch (simple, non-affiliate) ─────────────────────────
_PPH_JOB_RE = re.compile(r'href="(/job/\d+[^"]*)"[^>]*>([^<][^<]+)</a>', re.IGNORECASE)

async def pph_search(keyword: str) -> List[Dict]:
    """
    Scrape PeoplePerHour search results for jobs (no affiliate).
    Builds Original/Proposal as the canonical PPH job link.
    """
    q = keyword.strip()
    if not q:
        return []
    url = f"https://www.peopleperhour.com/freelance-jobs?q={quote_plus(q)}"  # <-- fixed
    cards: List[Dict] = []
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=HEADERS_HTML) as client:
            r = await client.get(url)
            if r.status_code != 200:
                log.warning("PPH fetch error for '%s': %s", keyword, r)
                return []
            html = r.text
    except Exception as e:
        log.warning("PPH fetch error for '%s': %s", keyword, e)
        return []

    seen_ids = set()
    for m in _PPH_JOB_RE.finditer(html):
        href = m.group(1)  # /job/123456-title...
        title = re.sub(r"\s+", " ", m.group(2)).strip()
        jid_m = re.search(r"/job/(\d+)", href)
        if not jid_m:
            continue
        jid = jid_m.group(1)
        if jid in seen_ids:
            continue
        seen_ids.add(jid)
        full_url = "https://www.peopleperhour.com" + href

        cards.append({
            "id": f"pph-{jid}",
            "source": "PeoplePerHour",
            "title": title or "Untitled",
            "type": None,
            "budget_local": "—",
            "budget_usd": None,
            "bids": None,
            "posted": "recent",
            "description": "",
            "proposal_url": full_url,
            "original_url": full_url,
        })

    log.info("PPH '%s': %d jobs", keyword, len(cards))
    return cards

# ───────────────────────── Match & Dedup ─────────────────────────
def job_matches(card: Dict, keywords: List[str]) -> bool:
    if not keywords:
        return True
    hay = []
    if JOB_MATCH_SCOPE in ("title", "title_desc"):
        hay.append(card.get("title") or "")
    if JOB_MATCH_SCOPE == "title_desc":
        hay.append(card.get("description") or "")
    hay_s = " ".join(hay).lower()

    kws = [k.lower() for k in keywords if k.strip()]
    if not kws:
        return True
    if JOB_MATCH_REQUIRE == "all":
        return all(k in hay_s for k in kws)
    return any(k in hay_s for k in kws)

def dedup_cards(cards: List[Dict]) -> List[Dict]:
    out: List[Dict] = []
    seen: set = set()
    for c in cards:
        jid = c.get("id")
        if jid and jid not in seen:
            out.append(c)
            seen.add(jid)
    return out

# ───────────────────────── Send helpers ─────────────────────────
async def send_job(chat_id: int, card: Dict, matched: Optional[List[str]] = None) -> None:
    txt = job_text({**card, "matched": matched or []})
    kb = card_markup(card)
    tg = await get_bot()
    await tg.send_message(
        chat_id=chat_id,
        text=txt,
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )

# ───────────────────────── Main loop per user ─────────────────────────
async def process_user(db: SessionLocal, u: User) -> int:
    now = now_utc()
    trial = to_aware(u.trial_until)
    lic = to_aware(u.access_until)
    active = (trial and trial >= now) or (lic and lic >= now)
    if not active or u.is_blocked:
        return 0

    keywords = [k.keyword for k in (u.keywords or [])]
    if not keywords:
        return 0

    all_cards: List[Dict] = []

    # Freelancer
    for kw in keywords:
        try:
            fl_cards = await freelancer_search(kw)
            for c in fl_cards:
                c["matched"] = [kw]
            all_cards.extend(fl_cards)
        except Exception as e:
            log.exception("Freelancer block error for kw='%s': %s", kw, e)

    # PeoplePerHour (non-affiliate)
    for kw in keywords:
        try:
            pph_cards = await pph_search(kw)
            for c in pph_cards:
                c["matched"] = [kw]
            all_cards.extend(pph_cards)
        except Exception as e:
            log.exception("PPH block error for kw='%s': %s", kw, e)

    # Filter & dedup
    filtered: List[Dict] = []
    for c in all_cards:
        if job_matches(c, keywords):
            filtered.append(c)
    filtered = dedup_cards(filtered)

    # Avoid re-sending already sent jobs
    already = {s.job_id for s in (u.sent_jobs or [])}
    to_send = [c for c in filtered if c.get("id") not in already]

    sent = 0
    for card in to_send:
        try:
            await send_job(int(u.telegram_id), card, matched=card.get("matched"))
            db.add(JobSent(user_id=u.id, job_id=card["id"], created_at=now_utc()))
            db.commit()
            log.info("Sent job %s to %s", card["id"], u.telegram_id)
            sent += 1
        except Exception as e:
            db.rollback()
            log.exception("Send job failed: %s", e)
    return sent

# ───────────────────────── Worker loop ─────────────────────────
async def worker_loop():
    ensure_schema()
    db = SessionLocal()
    try:
        log.info(
            "Worker loop every %ss (JOB_MATCH_SCOPE=%s, JOB_MATCH_REQUIRE=%s)",
            INTERVAL_SECS, JOB_MATCH_SCOPE, JOB_MATCH_REQUIRE
        )
    finally:
        db.close()

    while True:
        db = SessionLocal()
        total_sent = 0
        try:
            users = db.query(User).all()
            for u in users:
                try:
                    total_sent += await process_user(db, u)
                except Exception as e:
                    log.exception("User %s processing error: %s", u.telegram_id, e)
            log.info("Worker cycle complete. Sent %d messages.", total_sent)
        finally:
            db.close()
        await asyncio.sleep(INTERVAL_SECS)

# ───────────────────────── Entrypoint ─────────────────────────
if __name__ == "__main__":
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN env is required")
    asyncio.run(worker_loop())
