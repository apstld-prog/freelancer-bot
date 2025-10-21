# platform_peopleperhour.py — final version
# Unified format identical to Freelancer jobs
# Proxy first → fallback to direct scraping if empty or failed

import os, time, logging, re, httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from typing import List, Dict, Optional

log = logging.getLogger("pph")

API_KEY = os.getenv("API_KEY", "1211")
PPH_PROXY_URL = "https://pph-proxy-service.onrender.com/api/pph"
BASE_URL = "https://www.peopleperhour.com/freelance-jobs"
REQUEST_INTERVAL = 120  # seconds between safe requests
_last_request = 0.0

def _wait_safe():
    global _last_request
    elapsed = time.time() - _last_request
    if elapsed < REQUEST_INTERVAL:
        time.sleep(REQUEST_INTERVAL - elapsed)
    _last_request = time.time()

def _clean(t: Optional[str]) -> str:
    if not t:
        return ""
    return re.sub(r"\s+", " ", t).strip()

def _extract_budget(text: str):
    if not text:
        return None, None, None
    text = text.strip()
    m = re.search(r"([£€$])\s?([\d,]+)(?:\s*-\s*([£€$])?\s?([\d,]+))?", text)
    if not m:
        return None, None, None
    s1, v1, s2, v2 = m.groups()
    cur = s2 or s1
    try:
        v1 = float(v1.replace(",", ""))
        v2 = float(v2.replace(",", "")) if v2 else v1
    except Exception:
        return None, None, None
    symbol_map = {"£": "GBP", "$": "USD", "€": "EUR"}
    cur_code = symbol_map.get(cur, "GBP")
    return v1, v2, cur_code

def _humanize_ago(ts: float) -> str:
    now = time.time()
    diff = max(0, now - ts)
    if diff < 60:
        return "just now"
    m = int(diff // 60)
    if m < 60:
        return f"{m} min ago"
    h = m // 60
    if h < 24:
        return f"{h} h ago"
    d = h // 24
    if d < 7:
        return f"{d} d ago"
    return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")

def _parse_pph_page(html: str, keyword: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    cards = soup.select("section.job, div.job, li.job")
    if not cards:
        cards = soup.select("div.listing-card, article, div.search-result")
    for c in cards:
        title_el = c.select_one("a, h2, h3")
        if not title_el:
            continue
        title = _clean(title_el.get_text())
        desc_el = c.select_one("p, div.description, div.job__desc")
        desc = _clean(desc_el.get_text()) if desc_el else ""
        url = title_el.get("href", "")
        if url and not url.startswith("http"):
            url = "https://www.peopleperhour.com" + url

        budget_el = c.get_text()
        bmin, bmax, bcur = _extract_budget(budget_el)

        job = {
            "title": title,
            "description": desc,
            "budget_min": bmin,
            "budget_max": bmax,
            "budget_currency": bcur,
            "original_url": url,
            "source": "PeoplePerHour",
            "time_submitted": int(time.time()),
            "posted_ago": _humanize_ago(time.time()),
            "matched_keyword": keyword,
        }
        jobs.append(job)
    return jobs

def _fetch_via_proxy(keyword: str) -> List[Dict]:
    try:
        _wait_safe()
        url = f"{PPH_PROXY_URL}?key={API_KEY}&q={keyword}"
        r = httpx.get(url, timeout=30.0)
        if r.status_code != 200:
            log.warning("PPH proxy non-200: %s", r.status_code)
            return []
        data = r.json()
        if isinstance(data, dict) and "jobs" in data:
            data = data["jobs"]
        if not isinstance(data, list):
            return []
        jobs = []
        for j in data:
            job = {
                "title": _clean(j.get("title")),
                "description": _clean(j.get("description")),
                "budget_min": j.get("budget_min"),
                "budget_max": j.get("budget_max"),
                "budget_currency": j.get("budget_currency") or "GBP",
                "original_url": j.get("original_url"),
                "source": "PeoplePerHour",
                "time_submitted": int(j.get("time_submitted") or time.time()),
                "posted_ago": _humanize_ago(int(j.get("time_submitted") or time.time())),
                "matched_keyword": keyword,
            }
            jobs.append(job)
        return jobs
    except Exception as e:
        log.warning("PPH proxy fetch failed: %s", e)
        return []

def _fetch_via_scrape(keyword: str) -> List[Dict]:
    try:
        _wait_safe()
        params = {"q": keyword}
        r = httpx.get(BASE_URL, params=params, timeout=30.0)
        if r.status_code != 200:
            log.warning("PPH scrape non-200: %s", r.status_code)
            return []
        return _parse_pph_page(r.text, keyword)
    except Exception as e:
        log.warning("PPH scrape failed: %s", e)
        return []

def get_items(keywords: List[str]) -> List[Dict]:
    """Main entrypoint: returns list of PeoplePerHour jobs matching keywords"""
    all_jobs: List[Dict] = []
    for kw in keywords:
        kw = _clean(kw)
        if not kw:
            continue
        jobs = _fetch_via_proxy(kw)
        if not jobs:
            log.info("PPH proxy empty, fallback to scrape for '%s'", kw)
            jobs = _fetch_via_scrape(kw)
        all_jobs.extend(jobs)
    return all_jobs
