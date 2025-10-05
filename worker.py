# worker.py
import os
import re
import json
import logging
import unicodedata
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote_plus, urljoin

import httpx
import asyncio
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
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

INTERVAL_SECS = int(os.getenv("WORKER_INTERVAL_SECS", "300"))

JOB_MATCH_SCOPE = os.getenv("JOB_MATCH_SCOPE", "title_desc")  # title | title_desc
JOB_MATCH_REQUIRE = os.getenv("JOB_MATCH_REQUIRE", "any")     # any | all
MAX_PER_SOURCE = int(os.getenv("MAX_PER_SOURCE", "5"))

FREELANCER_REF_CODE = os.getenv("FREELANCER_REF_CODE", "").strip()

ENABLE_JOBFIND = os.getenv("ENABLE_JOBFIND", "1") == "1"
ENABLE_PPH = os.getenv("ENABLE_PPH", "1") == "1"
ENABLE_KARIERA = os.getenv("ENABLE_KARIERA", "1") == "1"

HTTP_TIMEOUT = 20.0
HEADERS_HTML = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) FreelancerAlertsBot/1.0"
}

# ───────────────────────── USD conversion ─────────────────────────
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

# ───────────────────────── Telegram client ─────────────────────────
bot: Optional[Bot] = None
async def get_bot() -> Bot:
    global bot
    if bot is None:
        bot = Bot(BOT_TOKEN)
    return bot

# ───────────────────────── Keyword helpers ─────────────────────────
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

def normalize_el(s: str) -> str:
    s = s.lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s

# Αγγλικά keyword → Ελληνικές ρίζες για GR boards
GREEK_SYNONYMS: Dict[str, List[str]] = {
    "lighting": ["φωτισμ"],
    "luminaire": ["φωτιστικ", "φωτιστικο", "φωτιστικων"],
    "led": ["led", "λεντ", "φωτιστικα led"],
    "logo": ["λογοτυπ", "λογκο"],
    "dialux": ["dialux", "ντιαλαξ"],
    "relux": ["relux", "ριλαξ"],
    "photometric": ["φωτομετρ", "φωτοτεχν", "φωτοτεχνικ"],
    "design": ["σχεδ", "μελετ", "σχεδιασμ"],
    "engineer": ["μηχανικ", "σχεδιαστ"],
    "project": ["εργο", "προτζεκτ", "μελετ"],
}

def greek_expansions_for(english_kw: str) -> List[str]:
    return GREEK_SYNONYMS.get(english_kw.lower(), [])

def title_matches(title: str, keywords: List[str], greek_mode: bool) -> bool:
    if not keywords:
        return True
    if greek_mode:
        hay = normalize_el(title or "")
        tokens = [normalize_el(t) for t in keywords if t.strip()]
    else:
        hay = (title or "").lower()
        tokens = [t.lower() for t in keywords if t.strip()]
    if not tokens:
        return True
    if JOB_MATCH_REQUIRE == "all":
        return all(t in hay for t in tokens)
    return any(t in hay for t in tokens)

# ───────────────────────── Render helpers ─────────────────────────
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

# ───────────────────────── Freelancer ─────────────────────────
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

# ───────────────────────── PeoplePerHour ─────────────────────────
_PPH_JOB_A = re.compile(r'href="(/job/\d+[^"]+)"[^>]*>([^<]+)</a>', re.IGNORECASE)
_PPH_DATA_ID = re.compile(r'data-job-id="(\d+)"[^>]*>.*?<a[^>]+href="(/job/\d+[^"]+)"[^>]*>([^<]+)</a>', re.IGNORECASE | re.DOTALL)
_PPH_MONEY = re.compile(r'([€£$])\s?(\d+(?:[.,]\d{1,2})?)', re.IGNORECASE)
_PPH_PER_HOUR = re.compile(r'per\s*hour|/hr|/hour', re.IGNORECASE)

def _money_to_code(sym: str) -> str:
    return {"€": "EUR", "£": "GBP", "$": "USD"}.get(sym, "USD")

async def pph_search(keyword: str) -> List[Dict]:
    q = keyword.strip()
    if not q:
        return []
    url = f"https://www.peopleperhour.com/freelance-jobs?q={quote_plus(q)}"
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

    def add_pph_card(jid: str, href: str, title: str, context: str):
        nonlocal cards
        if jid in seen_ids:
            return
        seen_ids.add(jid)
        full_url = urljoin("https://www.peopleperhour.com", href)

        minb = maxb = 0.0
        code = "USD"
        ptype = None
        usd_line = None
        local_line = "—"

        money = _PPH_MONEY.search(context)
        if money:
            sym, amt = money.group(1), money.group(2)
            amt_val = float(amt.replace(",", "."))
            code = _money_to_code(sym)
            minb = maxb = amt_val
            ptype = "Hourly" if _PPH_PER_HOUR.search(context) else "Fixed"
            local_line = fmt_local_budget(minb, maxb, code)
            usd_pair = to_usd(minb, maxb, code)
            if usd_pair:
                usd_line = fmt_usd_line(*usd_pair)

        cards.append({
            "id": f"pph-{jid}",
            "source": "PeoplePerHour",
            "title": title or "Untitled",
            "type": ptype,
            "budget_local": local_line,
            "budget_usd": usd_line,
            "bids": None,
            "posted": "recent",
            "description": "",
            "proposal_url": full_url,
            "original_url": full_url,
        })

    for m in _PPH_JOB_A.finditer(html):
        href = m.group(1)
        title = re.sub(r"\s+", " ", m.group(2)).strip()
        jid_m = re.search(r"/job/(\d+)", href)
        if not jid_m:
            continue
        jid = jid_m.group(1)
        start = max(0, m.start() - 300)
        end = min(len(html), m.end() + 300)
        context = html[start:end]
        add_pph_card(jid, href, title, context)

    for m in _PPH_DATA_ID.finditer(html):
        jid = m.group(1)
        href = m.group(2)
        title = re.sub(r"\s+", " ", m.group(3)).strip()
        start = max(0, m.start() - 300)
        end = min(len(html), m.end() + 300)
        context = html[start:end]
        add_pph_card(jid, href, title, context)

    log.info("PPH '%s': %d jobs", keyword, len(cards))
    return cards

# ───────────────────────── Kariera ─────────────────────────
_KAR_A = re.compile(r'href="(/jobs/[^"]+)"[^>]*>([^<]+)</a>', re.IGNORECASE)

async def kariera_search(keyword_el: str, greek_all_keywords: List[str]) -> List[Dict]:
    q = keyword_el.strip()
    if not q:
        return []
    url = f"https://www.kariera.gr/jobs?keyword={quote_plus(q)}"
    cards: List[Dict] = []
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=HEADERS_HTML) as client:
            r = await client.get(url)
            if r.status_code != 200:
                log.warning("Kariera fetch error for '%s': %s", keyword_el, r)
                return []
            html = r.text
    except Exception as e:
        log.warning("Kariera fetch error for '%s': %s", keyword_el, e)
        return []

    seen = set()
    for m in _KAR_A.finditer(html):
        href = m.group(1)
        title = re.sub(r"\s+", " ", m.group(2)).strip()
        if not title_matches(title, greek_all_keywords, greek_mode=True):
            continue
        jid = re.sub(r"[^a-zA-Z0-9]+", "-", href).strip("-")
        if jid in seen:
            continue
        seen.add(jid)
        full = urljoin("https://www.kariera.gr", href)
        cards.append({
            "id": f"kariera-{jid}",
            "source": "Kariera",
            "title": title or "Untitled",
            "type": None,
            "budget_local": "—",
            "budget_usd": None,
            "bids": None,
            "posted": "recent",
            "description": "",
            "proposal_url": full,
            "original_url": full,
        })
    log.info("Kariera '%s': %d jobs (post-filtered)", keyword_el, len(cards))
    return cards[:MAX_PER_SOURCE]

# ───────────────────────── JobFind ─────────────────────────
_JF_A = re.compile(r'href="(/job/[^"]+)"[^>]*>([^<]+)</a>', re.IGNORECASE)

async def _jobfind_fetch_html(keyword_el: str) -> Optional[str]:
    q = quote_plus(keyword_el.strip())
    candidates = [
        f"https://www.jobfind.gr/ergasia?keyword={q}",
        f"https://www.jobfind.gr/ergasia?keywords={q}",
        f"https://www.jobfind.gr/ergasia/search?keyword={q}",
        f"https://www.jobfind.gr/ergasia/el/search?keyword={q}",
    ]
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=HEADERS_HTML) as client:
        for url in candidates:
            try:
                r = await client.get(url)
                if r.status_code == 200 and r.text:
                    return r.text
                else:
                    log.info("JobFind probe %s → %s", url, r.status_code)
            except Exception as e:
                log.info("JobFind probe error %s → %s", url, e)
    return None

async def jobfind_search(keyword_el: str, greek_all_keywords: List[str]) -> List[Dict]:
    if not keyword_el.strip():
        return []
    html = await _jobfind_fetch_html(keyword_el)
    if not html:
        log.warning("JobFind fetch error for '%s': no working endpoint (404/redirects)", keyword_el)
        return []

    cards: List[Dict] = []
    seen = set()
    for m in _JF_A.finditer(html):
        href = m.group(1)
        title = re.sub(r"\s+", " ", m.group(2)).strip()
        if not title_matches(title, greek_all_keywords, greek_mode=True):
            continue
        jid = re.sub(r"[^a-zA-Z0-9]+", "-", href).strip("-")
        if jid in seen:
            continue
        seen.add(jid)
        full = urljoin("https://www.jobfind.gr", href)
        cards.append({
            "id": f"jobfind-{jid}",
            "source": "JobFind",
            "title": title or "Untitled",
            "type": None,
            "budget_local": "—",
            "budget_usd": None,
            "bids": None,
            "posted": "recent",
            "description": "",
            "proposal_url": full,
            "original_url": full,
        })
    log.info("JobFind '%s': %d jobs (post-filtered)", keyword_el, len(cards))
    return cards[:MAX_PER_SOURCE]

# ───────────────────────── Match & dedup ─────────────────────────
def job_matches(card: Dict, keywords: List[str]) -> bool:
    if not keywords:
        return True

    src = (card.get("source") or "").lower()
    is_gr = src in {"kariera", "jobfind"}

    hay_parts = []
    if JOB_MATCH_SCOPE in ("title", "title_desc"):
        hay_parts.append(card.get("title") or "")
    if JOB_MATCH_SCOPE == "title_desc":
        hay_parts.append(card.get("description") or "")
    hay = " ".join(hay_parts)

    if is_gr:
        hay_norm = normalize_el(hay)
        tokens = [normalize_el(k) for k in keywords if k.strip()]
        if not tokens:
            return True
        if JOB_MATCH_REQUIRE == "all":
            return all(t in hay_norm for t in tokens)
        return any(t in hay_norm for t in tokens)
    else:
        hay_s = hay.lower()
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
def job_card_with_match(card: Dict, kw: str) -> Dict:
    c = dict(card)
    c["matched"] = [kw]
    return c

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

    base_keywords = [k.keyword for k in (u.keywords or [])]
    if not base_keywords:
        return 0

    all_cards: List[Dict] = []

    # 1) Αγγλικές πλατφόρμες → ψάχνουμε ΜΟΝΟ με αγγλικά και δείχνουμε αγγλικό matched
    for kw_en in base_keywords:
        try:
            for c in await freelancer_search(kw_en):
                all_cards.append(job_card_with_match(c, kw_en))
        except Exception as e:
            log.exception("Freelancer block error for kw='%s': %s", kw_en, e)

    if ENABLE_PPH:
        for kw_en in base_keywords:
            try:
                for c in await pph_search(kw_en):
                    all_cards.append(job_card_with_match(c, kw_en))
            except Exception as e:
                log.exception("PPH block error for kw='%s': %s", kw_en, e)

    # 2) Ελληνικές πλατφόρμες → για κάθε αγγλικό, ψάχνουμε με ελληνικές ρίζες
    if ENABLE_KARIERA:
        for kw_en in base_keywords:
            greek_keys = greek_expansions_for(kw_en)
            for gkw in greek_keys:
                try:
                    for c in await kariera_search(gkw, greek_keys):
                        all_cards.append(job_card_with_match(c, gkw))  # δείχνει ελληνικό matched
                except Exception as e:
                    log.exception("Kariera block error for gkw='%s': %s", gkw, e)

    if ENABLE_JOBFIND:
        for kw_en in base_keywords:
            greek_keys = greek_expansions_for(kw_en)
            for gkw in greek_keys:
                try:
                    for c in await jobfind_search(gkw, greek_keys):
                        all_cards.append(job_card_with_match(c, gkw))  # ελληνικό matched
                except Exception as e:
                    log.exception("JobFind block error for gkw='%s': %s", gkw, e)

    # Filter & dedup
    filtered: List[Dict] = []
    for c in all_cards:
        src = (c.get("source") or "").lower()
        if src in {"kariera", "jobfind"}:
            keys_for_match = greek_expansions_for(c["matched"][0]) if c.get("matched") else base_keywords
            if not job_matches(c, keys_for_match,):
                continue
        else:
            if not job_matches(c, base_keywords):
                continue
        filtered.append(c)

    filtered = dedup_cards(filtered)

    already = {s.job_id for s in (u.sent_jobs or [])}
    to_send = [c for c in filtered if c.get("id") not in already]

    sent = 0
    for card in to_send[: max(1, MAX_PER_SOURCE * 4)]:
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
            "Worker loop every %ss (JOB_MATCH_SCOPE=%s, JOB_MATCH_REQUIRE=%s, MAX_PER_SOURCE=%s, ENABLE_PPH=%s, ENABLE_KARIERA=%s, ENABLE_JOBFIND=%s)",
            INTERVAL_SECS, JOB_MATCH_SCOPE, JOB_MATCH_REQUIRE, MAX_PER_SOURCE, ENABLE_PPH, ENABLE_KARIERA, ENABLE_JOBFIND
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
