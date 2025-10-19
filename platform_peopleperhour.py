# platform_peopleperhour.py — HTML (no-RSS) parser using search pages (server-side rendered)
# Keeps UI identical. Filters to fresh window via FRESH_WINDOW_HOURS (default 48).
# When called with keywords list, it will query PPH per-keyword and parse job cards.
import os, re, logging, math
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
import httpx
from bs4 import BeautifulSoup

log = logging.getLogger("pph")

FRESH_WINDOW_HOURS = int(os.getenv("FRESH_WINDOW_HOURS", "48"))
SEND_ALL = os.getenv("PPH_SEND_ALL", "0") == "1"  # if true, don't require keyword match
TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "15"))
BASE = "https://www.peopleperhour.com"

HEADERS = {
    "User-Agent": os.getenv("SCRAPER_UA", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.7",
}

def _now_utc():
    return datetime.now(timezone.utc)

def _minutes_ago_to_dt(text: str) -> Optional[datetime]:
    try:
        text = text.strip().lower()
        n = [int(x) for x in re.findall(r'\d+', text)]
        val = n[0] if n else 0
        if "minute" in text:  return _now_utc() - timedelta(minutes=val)
        if "hour" in text:    return _now_utc() - timedelta(hours=val)
        if "day" in text:     return _now_utc() - timedelta(days=val)
        if "month" in text:   return _now_utc() - timedelta(days=30*val)
        if "year" in text:    return _now_utc() - timedelta(days=365*val)
    except Exception:
        return None
    return None

def _parse_budget(text: str):
    # Examples: "Fixed Price ‑ $50", "Hourly ‑ $20 - $40"
    if not text:
        return None, None, "USD"
    ccy = "USD"
    m = re.findall(r'([$€£])?\s?(\d+(?:\.\d+)?)', text.replace(",", ""))
    vals = [float(b) for (_, b) in m] if m else []
    if "$" in text: ccy="USD"
    elif "€" in text: ccy="EUR"
    elif "£" in text: ccy="GBP"
    if not vals:
        return None, None, ccy
    if len(vals)==1:
        return vals[0], None, ccy
    return min(vals), max(vals), ccy

def _usd(v: Optional[float], ccy: str) -> Optional[float]:
    if v is None: return None
    rates = {"USD":1.0,"EUR":1.07,"GBP":1.24,"CAD":0.73,"AUD":0.66}
    rate = rates.get(ccy.upper(), 1.0)
    return round(v*rate, 2)

def _compose_item(card, kw: Optional[str]) -> Optional[Dict]:
    title_el = card.select_one("a[href*='/job/']")
    if not title_el:
        return None
    title = title_el.get_text(strip=True)
    url = title_el.get("href","")
    if url and url.startswith("/"):
        url = BASE + url

    desc_el = card.select_one(".JobSearchCard__Description, .BriefDescription")
    description = (desc_el.get_text(" ", strip=True) if desc_el else "")

    budget_el = card.select_one(".JobSearchCard__Budget, .Value")
    budget_text = budget_el.get_text(" ", strip=True) if budget_el else ""

    posted_el = card.select_one(".JobSearchCard__Info time, time")
    posted_text = posted_el.get_text(" ", strip=True).lower() if posted_el else ""
    posted_dt = _minutes_ago_to_dt(posted_text) if posted_text else None

    bmin,bmax,ccy = _parse_budget(budget_text)
    item = {
        "source": "peopleperhour",
        "title": title,
        "description": description,
        "url": url,
        "original_url": url,
        "budget_min": bmin,
        "budget_max": bmax,
        "budget_currency": ccy,
        "budget_min_usd": _usd(bmin, ccy),
        "budget_max_usd": _usd(bmax, ccy),
        "posted_at": posted_dt.isoformat() if posted_dt else None,
    }
    if kw: item["matched_keyword"] = kw
    return item

def _search_pages_for_keyword(kw: str, limit_pages: int = 2) -> List[Dict]:
    # Query parameters observed: /freelance-jobs?search=python
    items: List[Dict] = []
    q = kw.strip()
    if not q: 
        return items
    url = f"{BASE}/freelance-jobs?search={q}"
    with httpx.Client(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
        for page in range(1, limit_pages+1):
            u = url + (f"&page={page}" if page>1 else "")
            resp = client.get(u)
            if resp.status_code != 200:
                break
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("[data-automation-id='job-search-card'], .JobSearchCard, .job-card")
            for c in cards:
                it = _compose_item(c, kw)
                if it:
                    items.append(it)
    return items

def _fresh_filter(items: List[Dict]) -> List[Dict]:
    window = timedelta(hours=FRESH_WINDOW_HOURS)
    now = _now_utc()
    keep: List[Dict] = []
    for it in items:
        ts = it.get("posted_at") or it.get("created_at") or it.get("date")
        dt = None
        if ts:
            try:
                dt = datetime.fromisoformat(str(ts).replace("Z","+00:00"))
            except Exception:
                dt = None
        if dt is None:
            # If we can't parse, keep but prefer later in sort
            it["_score_time"] = now - timedelta(days=365*10)
            keep.append(it)
            continue
        if (now - dt) <= window:
            it["_score_time"] = dt
            keep.append(it)
    return keep

def _sort_dedupe(items: List[Dict]) -> List[Dict]:
    seen = set()
    out: List[Dict] = []
    items = sorted(items, key=lambda x: x.get("_score_time") or _now_utc(), reverse=True)
    for it in items:
        key = (it.get("url") or it.get("original_url") or it.get("title"))
        if key in seen: 
            continue
        seen.add(key)
        out.append(it)
    return out

def get_items(keywords: List[str]) -> List[Dict]:
    if not (os.getenv("ENABLE_PPH","0") == "1"):
        return []
    kws = [k for k in (keywords or []) if k and k.strip()]
    if not kws:
        return []

    collected: List[Dict] = []
    for kw in kws:
        try:
            collected.extend(_search_pages_for_keyword(kw, limit_pages=2))
        except Exception as e:
            log.debug("PPH search failed for %s: %s", kw, e)

    items = _fresh_filter(collected)
    items = _sort_dedupe(items)

    if not SEND_ALL and kws:
        # Ensure keyword match visible (already set), otherwise drop
        filtered = []
        for it in items:
            hay = (it.get("title","") + " " + it.get("description","")).lower()
            mk = it.get("matched_keyword")
            if mk and mk.lower() in hay:
                filtered.append(it)
        items = filtered

    return items
