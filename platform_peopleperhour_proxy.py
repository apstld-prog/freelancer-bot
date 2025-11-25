# platform_peopleperhour_proxy.py
# PeoplePerHour via Proxy JSON API v3
import httpx
import logging

log = logging.getLogger("pph")

BASE = "https://pph-proxy.onrender.com/api?page={page}"

TIMEOUT = httpx.Timeout(10.0, connect=5.0)
HEADERS = {
    "User-Agent": "FreelancerBot/1.0"
}

def _fetch_page(page: int):
    url = BASE.format(page=page)
    try:
        with httpx.Client(timeout=TIMEOUT, headers=HEADERS, verify=False) as c:
            r = c.get(url)
            if r.status_code != 200:
                log.warning(f"PPH page {page} HTTP {r.status_code}")
                return []
            js = r.json()
            items = js.get("items") or js.get("jobs") or []
            if not isinstance(items, list):
                return []
            return items
    except Exception as e:
        log.warning(f"PPH fetch error page {page}: {e}")
        return []

def fetch_all_pages(max_pages=5):
    out = []
    for p in range(1, max_pages + 1):
        arr = _fetch_page(p)
        if not arr:
            break
        out.extend(arr)
    return out

def _normalize(j):
    """Normalize PPH JSON job into BOT format."""
    title = j.get("title") or ""
    desc = j.get("description") or ""
    budget_min = j.get("minBudget")
    budget_max = j.get("maxBudget")
    currency = j.get("currencyCode") or j.get("currency") or "USD"
    ts = j.get("timestamp") or j.get("createdAt") or j.get("publishedAt")

    seo = j.get("seoUrl") or ""
    if seo.startswith("/"):
        link = "https://www.peopleperhour.com" + seo
    else:
        link = seo

    return {
        "title": title,
        "description": desc,
        "budget_min": budget_min,
        "budget_max": budget_max,
        "original_currency": currency,
        "url": link,
        "source": "PeoplePerHour",
        "timestamp": ts
    }

def get_items(keywords):
    raw = fetch_all_pages()
    items = [_normalize(j) for j in raw]

    out = []
    for it in items:
        txt = (it.get("title","") + " " + it.get("description","")).lower()
        for kw in keywords:
            if not kw:
                continue
            if kw.lower() in txt:
                x = it.copy()
                x["matched_keyword"] = kw
                out.append(x)
                break
    return out
