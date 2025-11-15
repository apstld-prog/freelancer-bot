# platform_peopleperhour.py — minimal always-on scraper
import httpx, re, random, time
from datetime import datetime, timezone
from typing import List, Dict

BASE_URL = "https://www.peopleperhour.com/freelance-jobs"
UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
]

def _client():
    return httpx.Client(headers={"User-Agent": random.choice(UAS)}, timeout=15, follow_redirects=True)

def _fetch(url: str) -> str:
    with _client() as c:
        time.sleep(0.1 + random.random()*0.2)
        r = c.get(url)
        if r.status_code in (429,503):
            time.sleep(1.2)
            r = c.get(url)
        r.raise_for_status()
        return r.text

def _clean(t): return re.sub(r"<.*?>","",t or "").strip()

def get_items(keywords: List[str]) -> List[Dict]:
    out=[]
    for kw in keywords or []:
        kw=kw.strip()
        if not kw: continue
        html=_fetch(f"{BASE_URL}?q={kw}")
        cards=re.findall(r'<div class="job-card.*?</div></div>',html,re.S)
        for card in cards[:20]:
            t=re.search(r'<h3[^>]*>(.*?)</h3>',card,re.S)
            title=_clean(t.group(1)) if t else "Untitled"
            h=re.search(r'href="(/freelance-jobs[^"]+)"',card)
            link="https://www.peopleperhour.com"+h.group(1) if h else ""
            d=re.search(r'<p[^>]*>(.*?)</p>',card,re.S)
            desc=_clean(d.group(1)) if d else ""
            out.append({
                "title":title,
                "description":desc,
                "url":link,
                "original_url":link,
                "source":"peopleperhour",
                "date":datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z"),
                "matched_keyword":kw
            })
    uniq=[]; seen=set()
    for it in out:
        if it["url"] not in seen:
            seen.add(it["url"]); uniq.append(it)
    return uniq
