import re
import time
from typing import List, Dict, Optional

import httpx
from bs4 import BeautifulSoup

from storage_redis import redis_client

BASE = "https://www.peopleperhour.com"
SEARCH_URL = BASE + "/freelance-jobs"

# TTL για cache ανά keyword (δευτερόλεπτα)
PPH_CACHE_TTL = 300  # 5 λεπτά


def _clean(text: Optional[str]) -> str:
    return (text or "").replace("\r", " ").replace("\n", " ").strip()


def _extract_budget(text: str):
    """
    Προσπαθεί να βρει min/max και currency από string τιμής.
    Πιάνει patterns όπως: "$100 - $200", "£150", "€50 - €80" κλπ.
    """
    if not text:
        return None, None, None

    pat = re.compile(r"([$\£\€])\s*([\d,]+(?:\.\d+)?)")
    matches = pat.findall(text)
    if not matches:
        return None, None, None

    vals = []
    currency = None
    for sym, num in matches:
        try:
            vals.append(float(num.replace(",", "")))
        except Exception:
            continue
        if not currency:
            if sym == "$":
                currency = "USD"
            elif sym == "£":
                currency = "GBP"
            elif sym == "€":
                currency = "EUR"

    if not vals:
        return None, None, currency

    return min(vals), max(vals), currency


def _scrape_search_keyword(keyword: str) -> List[Dict]:
    """
    Scrape ΜΟΝΟ την search σελίδα για 1 keyword (χωρίς Playwright).
    Επιστρέφει λίστα minimal job dicts.
    """
    kw = (keyword or "").strip()
    if not kw:
        return []

    params = {"q": kw}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/119.0.0.0 Safari/537.36"
        )
    }

    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            r = client.get(SEARCH_URL, params=params, headers=headers)
            r.raise_for_status()
            html = r.text
    except Exception:
        return []

    soup = BeautifulSoup(html, "html.parser")
    items: List[Dict] = []

    # Πιάνουμε τα job cards με ευέλικτο selector
    for li in soup.select("li[class*='list__item']"):
        try:
            title_el = li.select_one("h6[class*='item__title'] a")
            title = title_el.get_text(strip=True) if title_el else ""

            link = title_el.get("href") if title_el else ""
            if link and link.startswith("/"):
                link = BASE + link

            desc_el = li.select_one("p[class*='item__desc']")
            desc = desc_el.get_text(strip=True) if desc_el else ""

            price_el = li.select_one(".card__price span span")
            price_raw = (
                price_el.get_text(strip=True).replace("\u00A0", " ")
                if price_el
                else ""
            )
            bmin, bmax, cur = _extract_budget(price_raw)

            time_el = li.select_one(".card__footer-left span")
            timeago = time_el.get_text(strip=True) if time_el else ""
            
    # μετατροπή "5 hours ago", "8 hours ago" κλπ. σε timestamp ISO
        ts = None
        try:
            txt = timeago.lower()
            if "hour" in txt:
                num = int(re.findall(r"\d+", txt)[0])
                dt = datetime.utcnow() - timedelta(hours=num)
                ts = dt.isoformat() + "Z"
            elif "minute" in txt:
                num = int(re.findall(r"\d+", txt)[0])
                dt = datetime.utcnow() - timedelta(minutes=num)
                ts = dt.isoformat() + "Z"
            elif "day" in txt:
                num = int(re.findall(r"\d+", txt)[0])
                dt = datetime.utcnow() - timedelta(days=num)
                ts = dt.isoformat() + "Z"
        except Exception:
            ts = None

            items.append(
                {
                    "source": "peopleperhour",
                    "title": title,
                    "description": desc,
                    "description_html": desc,
                    "budget_min": bmin,
                    "budget_max": bmax,
                    "original_currency": cur,
                    "timestamp": ts,
                    "time_submitted": ts,
                    "original_url": link,
                    "proposal_url": link,
                    "price_raw": price_raw,
                    "time_ago": timeago,
                    "matched_keyword": kw.lower(),
                }
            )
        except Exception:
            continue

    return items


def _cache_key_for_keyword(keyword: str) -> str:
    return f"pph:search:{keyword.lower()}"


def get_items(keywords: List[str]) -> List[Dict]:
    """
    Public sync API για unified worker:
    - για κάθε keyword κοιτάει cache (Upstash Redis),
    - αν λείπει/έχει λήξει, κάνει 1 HTTP call στη PPH search σελίδα,
    - ενώνει/αποDeduplicates τα αποτελέσματα σε μία λίστα.
    """
    kws = [k.strip() for k in (keywords or []) if k and k.strip()]
    if not kws:
        return []

    out: List[Dict] = []
    seen_urls: set = set()

    now = int(time.time())

    for kw in kws:
        key = _cache_key_for_keyword(kw)
        cached = redis_client.get_json(key)
        if cached and isinstance(cached, dict):
            ts = cached.get("ts")  # timestamp αποθήκευσης
            jobs = cached.get("jobs") or []
            # απλή επιπλέον ασφάλεια: αν ts λείπει, αγνόησε την cache
            if ts and now - int(ts) <= PPH_CACHE_TTL:
                items = jobs
            else:
                items = _scrape_search_keyword(kw)
                redis_client.set_json(
                    key, {"ts": now, "jobs": items}, ttl_seconds=PPH_CACHE_TTL
                )
        else:
            items = _scrape_search_keyword(kw)
            redis_client.set_json(
                key, {"ts": now, "jobs": items}, ttl_seconds=PPH_CACHE_TTL
            )

        for it in items:
            url = it.get("original_url") or it.get("proposal_url")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            out.append(it)

    return out
