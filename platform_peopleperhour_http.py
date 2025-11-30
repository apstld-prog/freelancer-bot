import re
import time
from typing import List, Dict, Optional
from datetime import datetime, timedelta

import httpx
from bs4 import BeautifulSoup

from storage_redis import redis_client

BASE = "https://www.peopleperhour.com"
SEARCH_HTML_URL = BASE + "/freelance-jobs"
SEARCH_JSON_URL = BASE + "/search/projects"

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
       Scrape ΜΟΝΟ τα JSON search results για 1 keyword (χωρίς Playwright).
    Καλεί το /search/projects endpoint και γυρίζει minimal job dicts.
    """
    kw = (keyword or "").strip()
    if not kw:
        return []

# Σημείωση: το PPH JSON endpoint περιμένει 'keyword' και 'page'
params = {"keyword": kw, "page": 1}
headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/119.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}

try:
    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        r = client.get(SEARCH_JSON_URL, params=params, headers=headers)
        r.raise_for_status()
        data = r.json()
except Exception:
    return []

items: List[Dict] = []

# Προσαρμόζεις εδώ ανάλογα με τη δομή του JSON.
# Συνήθως θα είναι κάτι σαν {"projects": [ { .. ένα project .. }, ... ]}
projects = data.get("projects") if isinstance(data, dict) else None
if not projects and isinstance(data, list):
    projects = data

if not projects:
    return []

for p in projects:
    try:
        # Fields που περιμένουμε από το JSON – προσαρμόζεις στα πραγματικά keys
        title = _clean(p.get("title") or p.get("name") or "")
        # π.χ. "/freelance-jobs/xyz" ή πλήρες URL
        slug = p.get("url") or p.get("seo_url") or p.get("project_url") or ""
        link = slug or ""
        if link.startswith("/"):
            link = BASE + link

        desc = _clean(p.get("description") or p.get("summary") or "")

        # Budget αν υπάρχει σε ένα πεδίο price_text, αλλιώς από min/max fields
        price_text = p.get("price_text") or ""
        if not price_text:
            # Π.χ. min_price / max_price / currency_code
            min_price = p.get("min_price")
            max_price = p.get("max_price")
            currency_code = p.get("currency") or p.get("currency_code")
            # Αν υπάρχουν numeric fields, τα χρησιμοποιούμε
            if isinstance(min_price, (int, float)) or isinstance(max_price, (int, float)):
                bmin = float(min_price) if isinstance(min_price, (int, float)) else None
                bmax = float(max_price) if isinstance(max_price, (int, float)) else None
                cur = currency_code
            else:
                bmin, bmax, cur = None, None, None
        else:
            bmin, bmax, cur = _extract_budget(price_text)

        # posted_at: ISO 8601 string
        ts = None
        posted_at = p.get("posted_at") or p.get("created_at") or p.get("updated_at")
        if isinstance(posted_at, str) and posted_at.strip():
            ts = posted_at.strip()

        items.append(
            {
                "source": "peopleperhour",
                "title": title,
                "description": desc,
                "description_html": desc,
                "budget_min": bmin,
                "budget_max": bmax,
                "original_currency": cur,
                "timestamp": ts,          # ISO 8601 string ή None
                "time_submitted": ts,
                "original_url": link,
                "proposal_url": link,
                "price_raw": price_text,
                "time_ago": None,        # δεν το χρειαζόμαστε αν έχουμε posted_at
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
    - αν λείπει/έχει λήξει, κάνει 1 HTTP call στο PPH search JSON endpoint,
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
