# platform_peopleperhour.py — HTML scraping version (PeoplePerHour)
# Fully functional version for Freelancer Bot — 48h window, 10 pages, keyword filtering

import os, re, html, urllib.parse, logging, json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
import httpx

log = logging.getLogger("pph")

# ---------------- ENV CONFIG ----------------
FRESH_HOURS = int(os.getenv("PPH_FRESH_HOURS", "48"))
USER_AGENT = os.getenv("HTTP_USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
PPH_BASE_URL = os.getenv("PPH_BASE_URL", "https://www.peopleperhour.com/freelance-jobs?q={kw}&page={page}")
PPH_MAX_PAGES = int(os.getenv("PPH_MAX_PAGES", "10"))
PPH_INTERVAL_SECONDS = int(os.getenv("PPH_INTERVAL_SECONDS", "120"))
PPH_SEND_ALL = os.getenv("PPH_SEND_ALL", "0") == "1"
FX_RATES = json.loads(os.getenv("FX_RATES", '{"USD":1.0,"EUR":1.08,"GBP":1.26}'))
DEBUG_LOG = True  # force debug on for monitoring

_CURRENCY_MAP = {"£": "GBP", "€": "EUR", "$": "USD", "₹": "INR", "A$": "AUD", "C$": "CAD", "NZ$": "NZD"}
_SYM_ORDER = sorted(_CURRENCY_MAP.keys(), key=len, reverse=True)

# ---------------- HELPERS ----------------
def _strip_html(s: str) -> str:
    try:
        text = re.sub(r"<[^>]+>", " ", s or "", flags=re.S | re.I)
        return html.unescape(re.sub(r"\s+", " ", text)).strip()
    except Exception:
        return (s or "").strip()

def _match_keyword(title: str, description: str, keywords: List[str]) -> Optional[str]:
    hay = f"{(title or '').lower()} {(description or '').lower()}"
    for kw in keywords or []:
        if kw.lower() in hay:
            return kw
    return None

def _fetch(url: str, timeout: float = 15.0) -> str:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.peopleperhour.com/"
    }
    r = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    return r.text

def _extract_budget(text: str):
    for sym in _SYM_ORDER:
        m = re.search(rf"{re.escape(sym)}\s*(\d+(?:[\.,]\d+)?)", text)
        if m:
            val = float(m.group(1).replace(",", "."))
            return val, val, _CURRENCY_MAP.get(sym, sym)
    return None, None, None

def _extract_date(text: str) -> datetime:
    m = re.search(r"(\d+)\s+(hour|day)s?\s+ago", text, re.I)
    now = datetime.now(timezone.utc)
    if not m:
        return now
    val, unit = int(m.group(1)), m.group(2).lower()
    delta = timedelta(hours=val) if "hour" in unit else timedelta(days=val)
    return now - delta

def _convert_currency(amount: float, code: str) -> str:
    try:
        if code not in FX_RATES:
            return f"{amount:.2f} {code}"
        usd = amount / FX_RATES[code] if code != "USD" else amount
        eur = usd * FX_RATES["EUR"]
        return f"{amount:.0f} {code} (~${usd:.0f} USD / €{eur:.0f} EUR)"
    except Exception:
        return f"{amount:.0f} {code}"

# ---------------- SCRAPER ----------------
def _parse_job_card(card_html: str) -> Optional[Dict]:
    # Extract job URL
    m = re.search(r'href="(/job/\d+[^"]*)"', card_html)
    if not m:
        return None
    url = f"https://www.peopleperhour.com{m.group(1)}"

    # Title
    title_m = re.search(r'<h3[^>]*>(.*?)</h3>', card_html, re.S | re.I)
    title = _strip_html(title_m.group(1)) if title_m else "Untitled"

    # Description
    desc_m = re.search(r'<p[^>]*>(.*?)</p>', card_html, re.S | re.I)
    desc = _strip_html(desc_m.group(1)) if desc_m else ""

    # Budget
    budget_m = re.search(r'((?:£|€|\$|USD|EUR|GBP)\s*\d+(?:[\.,]\d+)?)', card_html)
    budget_min, budget_max, currency = _extract_budget(budget_m.group(1)) if budget_m else (None, None, None)

    # Date
    dt = _extract_date(card_html)

    return {
        "title": title,
        "description": desc,
        "url": url,
        "original_url": url,
        "budget_min": budget_min,
        "budget_max": budget_max,
        "currency": currency,
        "date": dt.strftime("%a, %d %b %Y %H:%M:%S %z"),
        "source": "peopleperhour"
    }

def _fetch_jobs_for_keyword(keyword: str) -> List[Dict]:
    jobs: List[Dict] = []
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=FRESH_HOURS)

    for page in range(1, PPH_MAX_PAGES + 1):
        url = PPH_BASE_URL.format(kw=urllib.parse.quote_plus(keyword), page=page)
        try:
            html_text = _fetch(url)
        except Exception as e:
            log.warning(f"[PPH] fetch failed ({keyword} p{page}): {e}")
            continue

        cards = re.findall(r'(<article[^>]*class="[^"]*job[^"]*"[^>]*>.*?</article>)', html_text, re.S | re.I)
        if not cards:
            break

        for card in cards:
            job = _parse_job_card(card)
            if not job:
                continue
            dt = datetime.strptime(job["date"], "%a, %d %b %Y %H:%M:%S %z")
            if dt < cutoff:
                continue
            match_kw = _match_keyword(job["title"], job["description"], [keyword])
            if not match_kw and not PPH_SEND_ALL:
                continue
            job["matched_keyword"] = match_kw or keyword
            if job["budget_min"] and job["currency"]:
                job["budget_display"] = _convert_currency(job["budget_min"], job["currency"])
            jobs.append(job)

        if DEBUG_LOG:
            log.info(f"[PPH] fetched {len(jobs)} jobs (kw={keyword}, page={page})")

    return jobs

# ---------------- MAIN ENTRY ----------------
def get_items(keywords: List[str]) -> List[Dict]:
    if not keywords:
        return []
    all_jobs: List[Dict] = []
    for kw in keywords:
        kw = kw.strip()
        if not kw:
            continue
        kw_jobs = _fetch_jobs_for_keyword(kw)
        all_jobs.extend(kw_jobs)
    # Remove duplicates
    uniq, seen = [], set()
    for j in all_jobs:
        uid = j["url"]
        if uid not in seen:
            seen.add(uid)
            uniq.append(j)
    if DEBUG_LOG:
        log.info(f"[PPH] Total {len(uniq)} jobs collected for {len(keywords)} keywords")
    return uniq
