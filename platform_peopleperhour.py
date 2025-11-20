# platform_peopleperhour.py
import httpx
import re
import random
import time
from typing import List, Dict, Optional

# ============================================================
# 🔵 PREMIUM PROXY POOL (STATIC – safe for PPH)
# ============================================================
PROXY_POOL = [
    "http://premium-proxy1.example:8000",
    "http://premium-proxy2.example:8000",
    "http://premium-proxy3.example:8000",
    "http://premium-proxy4.example:8000",
    "http://premium-proxy5.example:8000",
]

# ============================================================
# 🔵 HEADERS (anti-cloudflare)
# ============================================================
_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
    " AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]

BASE = "https://www.peopleperhour.com"

RE_ITEM = re.compile(r"<item>(.*?)</item>", re.S)
RE_TITLE = re.compile(r"<title>(.*?)</title>", re.S)
RE_LINK = re.compile(r"<link>(.*?)</link>", re.S)
RE_DATE = re.compile(r"<pubDate>(.*?)</pubDate>", re.S)
RE_DESC = re.compile(r"<description>(.*?)</description>", re.S)
SYM_ORDER = ["USD","GBP","EUR"]

# ============================================================
# 🔵 PROXY HTTP GET (με retry + 429 protection)
# ============================================================
def _proxy_get(url: str, timeout=6.0) -> Optional[str]:
    proxy = random.choice(PROXY_POOL)
    headers = {
        "User-Agent": random.choice(_UAS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": BASE,
        "Connection": "keep-alive"
    }

    for attempt in range(4):
        try:
            with httpx.Client(proxies=proxy, headers=headers, timeout=timeout, follow_redirects=True) as c:
                r = c.get(url)
                if r.status_code == 429:
                    time.sleep(1.0 + attempt)
                    continue
                if r.status_code >= 400:
                    return None
                return r.text
        except Exception:
            time.sleep(0.5 + attempt * 0.5)

    return None

# ============================================================
# 🔵 RSS PARSER (όπως το παλιό σου file)
# ============================================================
def _parse_rss_items(xml: str) -> List[Dict]:
    items=[]
    if not xml:
        return items

    raw_items = RE_ITEM.findall(xml)
    for block in raw_items:
        title = RE_TITLE.search(block)
        link = RE_LINK.search(block)
        desc = RE_DESC.search(block)
        date = RE_DATE.search(block)

        title = title.group(1).strip() if title else ""
        link = link.group(1).strip() if link else ""
        desc = desc.group(1).strip() if desc else ""
        date = date.group(1).strip() if date else ""

        if "peopleperhour.com" not in link:
            continue

        items.append({
            "title": title,
            "original_url": link,
            "proposal_url": link,
            "description_html": desc,
            "time_submitted": date,
            "budget_min": None,
            "budget_max": None,
            "currency": None,
            "currency_display": "USD",
            "source": "peopleperhour"
        })
    return items

# ============================================================
# 🔵 GET ITEMS (με KWs + RSS)
# ============================================================
def get_items(keywords: List[str]) -> List[Dict]:
    out=[]
    kws = [k.lower() for k in keywords]

    # --- Search RSS ---
    for kw in kws:
        url = f"{BASE}/freelance-jobs?rss=1&search={kw}"
        xml = _proxy_get(url)
        if not xml:
            continue

        parsed = _parse_rss_items(xml)
        for it in parsed:
            it["matched_keyword"] = kw
            out.append(it)

    # --- Fallback generic RSS ---
    if not out:
        url = f"{BASE}/freelance-jobs?rss=1&page=1"
        xml = _proxy_get(url)
        parsed = _parse_rss_items(xml)
        for it in parsed:
            for kw in kws:
                if kw in it["title"].lower():
                    it["matched_keyword"] = kw
                    out.append(it)

    return out
