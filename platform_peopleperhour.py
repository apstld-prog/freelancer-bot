# platform_peopleperhour.py — Enhanced scraping with premium proxies
import httpx, re, random, time
from typing import List, Dict, Optional

PROXY_POOL = [
    "http://premium-proxy1.example:8000",
    "http://premium-proxy2.example:8000",
    "http://premium-proxy3.example:8000",
    "http://premium-proxy4.example:8000",
    "http://premium-proxy5.example:8000",
]

_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17 Safari/605.1.15",
]

BASE = "https://www.peopleperhour.com"

RE_ITEM = re.compile(r"<item>(.*?)</item>", re.S)
RE_TITLE = re.compile(r"<title>(.*?)</title>", re.S)
RE_LINK = re.compile(r"<link>(.*?)</link>", re.S)
RE_DATE = re.compile(r"<pubDate>(.*?)</pubDate>", re.S)
RE_DESC = re.compile(r"<description>(.*?)</description>", re.S)

BUDGET_RE = re.compile(
    r"(\d+[.,]?\d*)\s*(USD|EUR|GBP)|\$(\d+[.,]?\d*)|€(\d+[.,]?\d*)|£(\d+[.,]?\d*)",
    re.I
)

def _proxy_get(url: str, timeout=8.0) -> Optional[str]:
    headers = {
        "User-Agent": random.choice(_UAS),
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": BASE,
        "Connection": "keep-alive"
    }
    for attempt in range(5):
        proxy = random.choice(PROXY_POOL)
        try:
            with httpx.Client(proxies=proxy, headers=headers, timeout=timeout, follow_redirects=True) as c:
                r = c.get(url)
                if r.status_code == 429:
                    time.sleep(1 + attempt)
                    continue
                if r.status_code >= 400:
                    return None
                return r.text
        except Exception:
            time.sleep(0.7 + attempt * 0.5)
    return None

def _parse_budget(text: str):
    mins = []
    maxs = []
    currency = "USD"
    for m in BUDGET_RE.findall(text):
        nums = [x for x in m if x.replace('.', '', 1).isdigit()]
        if nums:
            val = float(nums[0].replace(",", "."))
            mins.append(val)
            maxs.append(val)
        cur = [c for c in m if c in ["USD","EUR","GBP"]]
        if cur:
            currency = cur[0]
    if not mins:
        return None, None, None
    return min(mins), max(maxs), currency

def _scrape_job(url: str) -> Dict:
    html = _proxy_get(url)
    if not html:
        return {}
    budget_min, budget_max, cur = _parse_budget(html)
    return {
        "budget_min": budget_min,
        "budget_max": budget_max,
        "currency": cur,
        "currency_display": cur or "USD",
        "description": "",
    }

def _parse_rss_items(xml: str) -> List[Dict]:
    items=[]
    if not xml: return items
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
        scraped = _scrape_job(link)
        items.append({
            "title": title,
            "original_url": link,
            "proposal_url": link,
            "description": desc,
            "description_html": desc,
            "time_submitted": date,
            "source": "peopleperhour",
            **scraped
        })
    return items

def get_items(keywords: List[str]) -> List[Dict]:
    out=[]
    kws = [k.lower() for k in keywords]
    for kw in kws:
        url = f"{BASE}/freelance-jobs?rss=1&search={kw}"
        xml = _proxy_get(url)
        if not xml:
            continue
        parsed = _parse_rss_items(xml)
        for it in parsed:
            it["matched_keyword"] = kw
            out.append(it)
    if not out:
        url = f"{BASE}/freelance-jobs?rss=1&page=1"
        xml = _proxy_get(url)
        parsed = _parse_rss_items(xml)
        for it in parsed:
            for kw in kws:
                if kw in it.get("title","").lower():
                    it["matched_keyword"] = kw
                    out.append(it)
    return out
