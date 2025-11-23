# FINAL platform_peopleperhour_proxy.py
import httpx
import re
from typing import Dict, List, Optional
from config import PEOPLEPERHOUR_PROXY_URL

# regex helpers
RE_JOB_BLOCK = re.compile(r'<a[^>]+href="(/freelance-jobs/[^"]+)"[^>]*>(.*?)</a>', re.S)
RE_BUDGET = re.compile(r'(\d+[.,]?\d*)\s*(USD|EUR|GBP)|[$€£](\d+[.,]?\d*)', re.I)

def _proxy_fetch(url: str, timeout: float = 12.0) -> Optional[str]:
    try:
        r = httpx.get(f"{PEOPLEPERHOUR_PROXY_URL}/fetch", params={"url": url}, timeout=timeout)
        if r.status_code == 200:
            return r.text
    except Exception:
        return None
    return None

def _extract_budget(text: str):
    mins=[]; maxs=[]; cur="USD"
    for m in RE_BUDGET.findall(text or ""):
        nums = [x for x in m if x and x.replace('.', '', 1).isdigit()]
        if nums:
            val=float(nums[0].replace(",", "."))
            mins.append(val); maxs.append(val)
        cc=[x for x in m if x in ["USD","EUR","GBP"]]
        if cc: cur=cc[0]
    if not mins:
        return None, None, None
    return min(mins), max(maxs), cur

def get_items(keywords: List[str]) -> List[Dict]:
    out=[]
    for kw in keywords:
        search_url = f"https://www.peopleperhour.com/freelance-jobs?search={kw}"
        html = _proxy_fetch(search_url)
        if not html:
            continue

        # find job links
        for link, title in RE_JOB_BLOCK.findall(html):
            job_url = f"https://www.peopleperhour.com{link}"
            job_html = _proxy_fetch(job_url) or ""
            bmin, bmax, cur = _extract_budget(job_html)

            out.append({
                "source": "peopleperhour",
                "matched_keyword": kw,
                "title": re.sub('<.*?>', '', title).strip(),
                "original_url": job_url,
                "proposal_url": job_url,
                "description": "",
                "description_html": "",
                "budget_min": bmin,
                "budget_max": bmax,
                "currency": cur,
                "time_submitted": None,
            })
    return out
