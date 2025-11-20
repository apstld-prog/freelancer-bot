# platform_peopleperhour.py
import os, random, time, httpx
from typing import List, Dict, Optional
from bs4 import BeautifulSoup

ENABLE_PPH = True
PPH_PROXY_MODE = "premium"
PPH_INTERVAL = 180

PROXY_POOL = [
    "http://23.226.74.98:8080",
    "http://45.153.241.13:8000",
    "http://185.199.229.156:7492",
    "http://45.93.80.118:8080",
    "http://51.159.0.236:2020",
]

HEADERS_LIST = [
    {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    {"User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64)"},
]

SEARCH_URL = "https://www.peopleperhour.com/freelance-jobs?search={kw}"

def _get(url: str) -> Optional[str]:
    for _ in range(2):
        proxy = random.choice(PROXY_POOL)
        headers = random.choice(HEADERS_LIST)
        try:
            with httpx.Client(timeout=6.0) as c:
                r = c.get(url, headers=headers, proxies=proxy, follow_redirects=True)
            if r.status_code == 429:
                time.sleep(random.uniform(1.0, 2.0))
                continue
            if r.status_code == 200:
                return r.text
        except:
            continue
    return None

def _parse_listings(html: str, kw: str) -> List[Dict]:
    out=[]
    if not html:
        return out
    soup = BeautifulSoup(html, "html.parser")
    jobs = soup.select("a")
    for a in jobs:
        title = a.get_text(strip=True)
        href = a.get("href", "")
        if "/freelance-jobs/" not in href:
            continue
        if kw.lower() not in title.lower():
            continue
        out.append({
            "title": title,
            "original_url": "https://www.peopleperhour.com" + href,
            "source": "peopleperhour",
            "matched_keyword": kw
        })
    return out

def get_items(keywords: List[str]) -> List[Dict]:
    results=[]
    for kw in keywords:
        url = SEARCH_URL.format(kw=kw)
        html = _get(url)
        items = _parse_listings(html, kw)
        results.extend(items)
    return results
