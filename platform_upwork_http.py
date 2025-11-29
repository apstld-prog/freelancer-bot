# platform_upwork_http.py — simple Upwork scraper via HTML + cookies
#
# - Χρησιμοποιεί UPWORK_COOKIES από τα env vars (μία γραμμή τύπου "k1=v1; k2=v2")
# - Κάνει search στη σελίδα jobs της Upwork με query=keywords
# - Επιστρέφει normalized dicts συμβατά με τον unified worker (σαν το platform_freelancer)
#
# ΣΗΜΕΙΩΣΗ:
# - Αυτός ο scraper βασίζεται σε HTML structure της Upwork, που μπορεί να αλλάξει.
# - Χρησιμοποίησέ τον με ήπιο ρυθμό, shared cache και σεβασμό στους όρους χρήσης της Upwork.

from typing import List, Dict, Optional
import os
import time
import math
import datetime
import random   # ΝΕΟ

import httpx
from bs4 import BeautifulSoup

UPWORK_SEARCH_URL = "https://www.upwork.com/nx/search/jobs"  # HTML search page

# Optional: simple in-process cache για να μην βαράμε συνέχεια
_CACHE: Dict[str, Dict] = {}
CACHE_TTL_SECONDS = 600  # 10 λεπτά

def _now_ts() -> float:
    return time.time()

def _from_cache(key: str) -> Optional[List[Dict]]:
    entry = _CACHE.get(key)
    if not entry:
        return None
    if _now_ts() - entry["ts"] > CACHE_TTL_SECONDS:
        return None
    return entry.get("items") or []

def _to_cache(key: str, items: List[Dict]) -> None:
    _CACHE[key] = {"ts": _now_ts(), "items": items}

def _safe_num(x) -> Optional[float]:
    try:
        if x is None:
            return None
        f = float(x)
        if math.isnan(f):
            return None
        return round(f, 1)
    except Exception:
        return None

def _extract_budget(block: BeautifulSoup) -> (Optional[float], Optional[float], Optional[str]):
    """
    Προσπαθεί να βρει budget + currency μέσα στο block του job.
    Η Upwork αλλάζει συχνά layout, οπότε εδώ γίνεται best-effort parsing.
    """
    try:
        # Συνήθως υπάρχει κείμενο όπως "$10.00 - $30.00" ή "Fixed-price - Expert - Est. Budget: $50"
        text = block.get_text(" ", strip=True)
        # Πολύ απλό heuristic: ψάχνουμε για σύμβολα $ € £ κτλ.
        ccys = ["$", "€", "£"]
        currency = None
        for c in ccys:
            if c in text:
                currency = c
                break

        # Αναζητούμε 1 ή 2 αριθμούς (min/max)
        import re
        nums = re.findall(r"([0-9]+(?:\.[0-9]+)?)", text)
        if not nums:
            return None, None, None
        if len(nums) == 1:
            mn = _safe_num(nums[0])
            mx = None
        else:
            mn = _safe_num(nums[0])
            mx = _safe_num(nums[1])
        return mn, mx, currency
    except Exception:
        return None, None, None

def _extract_time(block: BeautifulSoup) -> (Optional[int], Optional[str]):
    """
    Προσπαθεί να πάρει relative/absolute time και να το γυρίσει σε epoch+ISO.
    Αν δεν βρούμε κάτι αξιόπιστο, επιστρέφουμε None.
    """
    try:
        # Πολλές φορές η Upwork βάζει κείμενο τύπου "Posted 3 hours ago"
        text = block.get_text(" ", strip=True).lower()
        import re
        m = re.search(r"posted\s+(\d+)\s+(minute|minutes|hour|hours|day|days)\s+ago", text)
        ts = None
        if m:
            num = int(m.group(1))
            unit = m.group(2)
            delta = 0
            if "minute" in unit:
                delta = num * 60
            elif "hour" in unit:
                delta = num * 3600
            elif "day" in unit:
                delta = num * 86400
            ts = int(_now_ts() - delta)
        if ts is None:
            return None, None
        iso = datetime.datetime.utcfromtimestamp(ts).isoformat() + "Z"
        return ts, iso
    except Exception:
        return None, None

def _normalize_job(card: BeautifulSoup) -> Optional[Dict]:
    """
    Παίρνει ένα job card (HTML) και βγάζει normalized dict.
    """
    try:
        # Τίτλος + URL
        title_el = card.select_one("a[data-test='job-title-link'], a.up-card-section--job-title")
        if not title_el:
            return None
        title = (title_el.get_text(strip=True) or "").strip()
        href = title_el.get("href") or ""
        if href.startswith("/"):
            url = "https://www.upwork.com" + href
        else:
            url = href

        # Περιγραφή (σύντομη)
        desc_el = card.select_one("[data-test='job-description-text'], div[data-test='job-description']")
        description = ""
        if desc_el:
            description = desc_el.get_text(" ", strip=True).strip()

        # Budget + currency
        budget_min, budget_max, currency_symbol = _extract_budget(card)

        # Χρόνος
        ts, iso = _extract_time(card)

        out: Dict = {
            "source": "upwork",
            "title": title,
            "description": description,
            "original_url": url,
            "budget_min": budget_min,
            "budget_max": budget_max,
            "original_currency": None,   # Δεν έχουμε ISO code, μόνο symbol
            "currency_symbol": currency_symbol,
            "time_submitted": ts,
            "time_submitted_iso": iso,
        }
        # Για συνέπεια με freelancer: currency_display + currency
        out["currency_display"] = currency_symbol or "USD"
        out["currency"] = None
        return out
    except Exception:
        return None

def _build_headers() -> Dict[str, str]:
    cookies = os.environ.get("UPWORK_COOKIES", "").strip()

    # Μπορείς αν θέλεις να βάλεις εδώ ακριβώς το User-Agent από τον browser σου
    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/129.0.0.0 Safari/537.36"
    )

    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
        "Referer": "https://www.upwork.com/ab/jobs/search/",  # κλασική σελίδα job search
    }
    if cookies:
        headers["Cookie"] = cookies
    return headers

def fetch_html(keywords_query: str) -> List[Dict]:
    """
    Κάνει ένα search request στη σελίδα jobs της Upwork και κάνει parse τα job cards.
    """
    cache_key = f"upwork:{keywords_query}"
    cached = _from_cache(cache_key)
    if cached is not None:
        return cached

    params = {
        "q": keywords_query,
        "sort": "recency",
    }
    headers = _build_headers()
    items: List[Dict] = []

    try:
        # Μικρό τυχαίο delay 0.5–2.0 sec για να μη φαίνεται “ρομπότ”
        time.sleep(random.uniform(0.5, 2.0))

        with httpx.Client(timeout=15.0, follow_redirects=True) as cli:
            r = cli.get(UPWORK_SEARCH_URL, params=params, headers=headers)
            r.raise_for_status()
            html = r.text
    except Exception:
        return []


    try:
        soup = BeautifulSoup(html, "html.parser")
        # Job cards: η Upwork συνήθως έχει <section> ή <article> ανά job.
        # Χρησιμοποιούμε γενικό selector για να μη σπάσει εύκολα.
        cards = soup.select("section[data-test='job-tile'], article[data-test='job-tile']")
        for card in cards:
            it = _normalize_job(card)
            if it:
                items.append(it)
    except Exception:
        return []

    _to_cache(cache_key, items)
    return items

# ------------------------------------------------------------
# Public keyword-based interface (used by unified worker)
# ------------------------------------------------------------

def get_items(keywords: List[str]) -> List[Dict]:
    """
    Public keyword-based interface (used by unified worker).
    Παίρνει λίστα keywords και γυρίζει normalized jobs από Upwork.
    """
    if not keywords:
        return []

    q = ",".join(keywords)
    raw = fetch_html(q)

    out: List[Dict] = []
    for it in raw:
        text = f"{it.get('title','').lower()} {it.get('description','').lower()}"
        matched = None
        for kw in keywords:
            if kw.lower() in text:
                matched = kw
                break
        if matched:
            x = it.copy()
            x["matched_keyword"] = matched
            x["source"] = "upwork"
            out.append(x)
    return out
