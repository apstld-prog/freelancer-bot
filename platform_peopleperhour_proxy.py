# platform_peopleperhour_proxy.py
import httpx
import re
from typing import Dict, List, Optional
from config import PEOPLEPERHOUR_PROXY_URL

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
            val=float(nums[0].replace(",",".")); mins.append(val); maxs.append(val)
        cc=[x for x in m if x in ["USD","EUR","GBP"]]
        if cc: cur=cc[0]
    if not mins: return None,None,None
    return min(mins), max(maxs), cur

def _parse_rss_items(xml: str) -> List[Dict]:
    items=[]
    if not xml: return items
    raw=RE_ITEM.findall(xml)
    for block in raw:
        title = (RE_TITLE.search(block) or ["",""]).group(1).strip()
        link  = (RE_LINK.search(block) or ["",""]).group(1).strip()
        desc  = (RE_DESC.search(block) or ["",""]).group(1).strip()
        date  = (RE_DATE.search(block) or ["",""]).group(1).strip()

        items.append({
            "source": "peopleperhour",
            "title": title,
            "description": desc,
            "description_html": desc,
            "original_url": link,
            "proposal_url": link,
            "time_submitted": None,
        })
    return items

def _fetch_via_proxy(url: str, timeout=12.0) -> Optional[str]:
    if not PEOPLEPERHOUR_PROXY_URL:
        return None

    try:
        r = httpx.get(
            PEOPLEPERHOUR_PROXY_URL,
            params={"url": url},
            timeout=timeout,
        )
        if r.status_code == 200:
            return r.text
    except:
        return None
    return None

def get_items(keywords: List[str]) -> List[Dict]:
    out=[]
    for kw in keywords:
        url = f"https://www.peopleperhour.com/freelance-jobs?rss=1&search={kw}"
        xml = _fetch_via_proxy(url)
        if not xml:
            continue
        for item in _parse_rss_items(xml):
            item["matched_keyword"] = kw

            # fetch job page for budget
            job_html = _fetch_via_proxy(item["original_url"])
            bmin,bmax,cur = _parse_budget(job_html or "")
            item["budget_min"] = bmin
            item["budget_max"] = bmax
            item["currency"] = cur

            out.append(item)

    return out
