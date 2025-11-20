# platform_peopleperhour.py — FULL CIRCUMVENT MODE
import httpx, random, time, re
from typing import List, Dict, Optional

# FULL bypass-style pool (placeholders)
PROXY_POOL = [
    "http://pph-exit-1.resi:8000",
    "http://pph-exit-2.resi:8000",
    "http://pph-exit-3.resi:8000",
    "http://pph-exit-4.resi:8000",
    "http://pph-exit-5.resi:8000",
]

_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605 Safari/605.1.15",
]

BASE = "https://www.peopleperhour.com"

def _proxy_get(url: str, timeout=12.0) -> Optional[str]:
    for attempt in range(6):
        proxy = random.choice(PROXY_POOL)
        headers = {
            "User-Agent": random.choice(_UAS),
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": BASE,
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
        try:
            with httpx.Client(
                proxies=proxy,
                headers=headers,
                timeout=timeout,
                follow_redirects=True,
                verify=False
            ) as c:
                r = c.get(url)
                if r.status_code in (403,429):
                    time.sleep(1.2 + attempt*0.8)
                    continue
                if r.status_code >= 400:
                    return None
                return r.text
        except:
            time.sleep(0.5 + attempt*0.6)
    return None

RE_ITEM = re.compile(r"<item>(.*?)</item>", re.S)
RE_TITLE = re.compile(r"<title>(.*?)</title>", re.S)
RE_LINK = re.compile(r"<link>(.*?)</link>", re.S)
RE_DATE = re.compile(r"<pubDate>(.*?)</pubDate>", re.S)
RE_DESC = re.compile(r"<description>(.*?)</description>", re.S)

def _parse_budget(text: str):
    pat = re.compile(r"(\d+[.,]?\d*)\s*(USD|EUR|GBP)|[$€£](\d+[.,]?\d*)", re.I)
    mins=[]; maxs=[]; cur="USD"
    for m in pat.findall(text):
        nums=[x for x in m if x and x.replace('.','',1).isdigit()]
        if nums:
            val=float(nums[0].replace(",","."))
            mins.append(val)
            maxs.append(val)
        cc=[x for x in m if x in ["USD","EUR","GBP"]]
        if cc: cur=cc[0]
    if not mins: return None,None,None
    return min(mins), max(maxs), cur

def _scrape_job(url: str) -> Dict:
    html=_proxy_get(url)
    if not html: return {}
    bmin,bmax,cur=_parse_budget(html)
    return {
        "budget_min": bmin,
        "budget_max": bmax,
        "currency": cur,
        "currency_display": cur or "USD",
        "description": "",
    }

def _parse_rss_items(xml: str) -> List[Dict]:
    items=[]
    if not xml: return items
    raw=RE_ITEM.findall(xml)
    for block in raw:
        title=RE_TITLE.search(block)
        link=RE_LINK.search(block)
        desc=RE_DESC.search(block)
        date=RE_DATE.search(block)
        title=title.group(1).strip() if title else ""
        link=link.group(1).strip() if link else ""
        desc=desc.group(1).strip() if desc else ""
        date=date.group(1).strip() if date else ""
        if "peopleperhour.com" not in link:
            continue
        scraped=_scrape_job(link)
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
    kws=[k.lower() for k in keywords]
    for kw in kws:
        url=f"{BASE}/freelance-jobs?rss=1&search={kw}"
        xml=_proxy_get(url)
        if xml:
            parsed=_parse_rss_items(xml)
            for it in parsed:
                it["matched_keyword"]=kw
                out.append(it)
    if not out:
        url=f"{BASE}/freelance-jobs?rss=1&page=1"
        xml=_proxy_get(url)
        parsed=_parse_rss_items(xml)
        for it in parsed:
            for kw in kws:
                if kw in it.get("title","").lower():
                    it["matched_keyword"]=kw
                    out.append(it)
    return out
