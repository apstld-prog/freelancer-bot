# platform_peopleperhour.py — SAFE MODE via Proxy, 10 pages per keyword, no duplicate job pages

import httpx, time, re
from typing import List, Dict, Optional

PPH_PROXY = "https://pph-proxy-chris.fly.dev/?url="

BASE = "https://www.peopleperhour.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"

# Regex parsers
RE_ITEM = re.compile(r"<item>(.*?)</item>", re.S)
RE_TITLE = re.compile(r"<title>(.*?)</title>", re.S)
RE_LINK = re.compile(r"<link>(.*?)</link>", re.S)
RE_DATE = re.compile(r"<pubDate>(.*?)</pubDate>", re.S)
RE_DESC = re.compile(r"<description>(.*?)</description>", re.S)

def _proxy_get(url: str, timeout=25) -> Optional[str]:
    """Fetch via proxy only. SAFE MODE."""
    proxy_url = f"{PPH_PROXY}{url}"
    try:
        r = httpx.get(proxy_url, timeout=timeout, headers={"User-Agent": USER_AGENT})
        if r.status_code == 200:
            return r.text
    except Exception:
        return None
    return None

def _parse_budget(text: str):
    pat = re.compile(r"(\d+[.,]?\d*)\s*(USD|EUR|GBP)|[$€£](\d+[.,]?\d*)", re.I)
    mins=[]; maxs=[]; cur="USD"
    for m in pat.findall(text):
        nums=[x for x in m if x and x.replace('.','',1).isdigit()]
        if nums:
            val=float(nums[0].replace(",",".")); mins.append(val); maxs.append(val)
        cc=[x for x in m if x in ["USD","EUR","GBP"]]
        if cc: cur=cc[0]
    if not mins: return None,None,None
    return min(mins), max(maxs), cur

def _scrape_job(url: str) -> Dict:
    """Fetch job HTML and extract budget only."""
    html = _proxy_get(url)
    if not html:
        return {"budget_min": None, "budget_max": None, "currency": None, "currency_display": None}

    bmin,bmax,cur = _parse_budget(html)
    return {
        "budget_min": bmin,
        "budget_max": bmax,
        "currency": cur,
        "currency_display": cur or "USD",
    }

def _parse_rss_items(xml: str) -> List[Dict]:
    if not xml: return []
    out=[]
    blocks=RE_ITEM.findall(xml)
    for block in blocks:
        title=RE_TITLE.search(block)
        link=RE_LINK.search(block)
        desc=RE_DESC.search(block)
        date=RE_DATE.search(block)

        title = title.group(1).strip() if title else ""
        link = link.group(1).strip() if link else ""
        desc = desc.group(1).strip() if desc else ""
        date = date.group(1).strip() if date else ""

        if "peopleperhour.com" not in link:
            continue

        out.append({
            "title": title,
            "original_url": link,
            "proposal_url": link,
            "description": desc,
            "description_html": desc,
            "time_submitted": date,
            "source": "peopleperhour",
        })
    return out

def get_items(keywords: List[str]) -> List[Dict]:
    """SAFE MODE: Fetch 10 pages per keyword, no duplicate job pages."""
    final=[]
    seen_links=set()

    for kw in keywords:
        kw_lower = kw.lower()

        # 10 RSS pages
        for page in range(1, 11):
            rss_url = f"{BASE}/freelance-jobs?rss=1&search={kw_lower}&page={page}"
            xml = _proxy_get(rss_url)

            if not xml:
                continue

            parsed = _parse_rss_items(xml)

            for it in parsed:
                link = it["original_url"]
                if link in seen_links:
                    continue  # skip duplicates job pages

                seen_links.add(link)

                # Fetch budget
                jobdata = _scrape_job(link)
                it.update(jobdata)

                it["matched_keyword"] = kw_lower
                final.append(it)

            time.sleep(0.2)

    return final
