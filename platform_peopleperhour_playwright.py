# platform_peopleperhour_playwright.py
# --------------------------------------
# Playwright async scraper -> Fly.io proxy -> Fallback
#
# - Extracts full job data (title, budget min/max, currency, description HTML)
# - Uses external proxy: https://pph-proxy-chris.fly.dev/?url=
# - Fully async-compatible for Render unified worker
# --------------------------------------

import httpx
import asyncio
import re
from typing import Dict, List, Optional

PROXY_BASE = "https://pph-proxy-chris.fly.dev/?url="

BASE = "https://www.peopleperhour.com"

# --------------------------------------
# Helpers
# --------------------------------------

async def _fetch(url: str, timeout: float = 20.0) -> Optional[str]:
    """
    Fetch through Fly proxy (Playwright backend).
    Returns full HTML if successful.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
            r = await c.get(PROXY_BASE + url)
            if r.status_code == 200 and r.text:
                return r.text
    except Exception:
        return None
    return None


def _clean(text: str) -> str:
    return (text or "").replace("\n", " ").replace("\r", " ").strip()


def _extract_budget(html: str):
    """
    Extract min/max price and currency.
    Supports:
        £100
        $200
        €150
    """
    if not html:
        return None, None, None

    pat = re.compile(r"([$£€])\s?(\d+[.,]?\d*)")
    matches = pat.findall(html)

    if not matches:
        return None, None, None

    vals = []
    currency = None

    for sym, num in matches:
        try:
            vals.append(float(num.replace(",", ".")))
        except:
            continue
        if not currency:
            if sym == "$":
                currency = "USD"
            elif sym == "£":
                currency = "GBP"
            elif sym == "€":
                currency = "EUR"

    if not vals:
        return None, None, currency

    return min(vals), max(vals), currency


def _extract_description(html: str) -> str:
    """
    Extracts <div class="job-description">...</div>
    """
    m = re.search(r'<div class="job-description">(.*?)</div>', html, re.S)
    if m:
        return m.group(1).strip()
    return ""


def _extract_title(html: str) -> str:
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    return _clean(m.group(1)) if m else ""


def _extract_date(html: str) -> Optional[int]:
    """
    Extracts epoch timestamp embedded in PPH pages.
    Looks for: data-published="1698765432"
    """
    m = re.search(r'data-published="(\d+)"', html)
    if m:
        try:
            return int(m.group(1))
        except:
            return None
    return None


# --------------------------------------
# Scrape a single job
# --------------------------------------

async def _scrape_job(url: str) -> Dict:
    html = await _fetch(url)
    if not html:
        return {
            "budget_min": None,
            "budget_max": None,
            "currency": None,
            "description_html": "",
        }

    title = _extract_title(html)
    desc = _extract_description(html)
    bmin, bmax, cur = _extract_budget(html)
    ts = _extract_date(html)

    return {
        "title": title,
        "description": desc,
        "description_html": desc,
        "budget_min": bmin,
        "budget_max": bmax,
        "currency": cur,
        "time_submitted": ts,
    }


# --------------------------------------
# Fetch RSS-style job list
# --------------------------------------

async def _search_urls(keyword: str) -> List[str]:
    """
    RSS feed per keyword.
    """
    rss_url = f"{BASE}/freelance-jobs?rss=1&search={keyword}"
    xml = await _fetch(rss_url)
    if not xml:
        return []

    links = re.findall(r"<link>(.*?)</link>", xml)
    return [l.strip() for l in links if BASE in l]


# --------------------------------------
# PUBLIC API
# --------------------------------------

async def get_items_async(keywords: List[str]) -> List[Dict]:
    """
    Full async keyword fetch + scrape each job page.
    """
    out: List[Dict] = []

    for kw in keywords:
        kw = kw.strip().lower()
        links = await _search_urls(kw)

        for url in links[:10]:  # limit to 10 per keyword
            data = await _scrape_job(url)
            data["original_url"] = url
            data["proposal_url"] = url
            data["source"] = "peopleperhour"
            data["matched_keyword"] = kw
            out.append(data)

    return out


# Render worker calls this (sync wrapper)
def get_items(keywords: List[str]) -> List[Dict]:
    return asyncio.run(get_items_async(keywords))
