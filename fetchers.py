# fetchers.py — platform adapters (Skywalker live + Freelancer HTML + placeholders), USD conversion
from __future__ import annotations
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

import httpx

from db_events import _hash_for
from config import AFFILIATE_PREFIX

# ---------------- Currency helper (placeholder rates) ----------------
FX_USD = {
    "USD": 1.0, "EUR": 1.08, "GBP": 1.26, "PLN": 0.25, "RON": 0.22, "HUF": 0.0027,
}

def to_usd(amount: Optional[float], currency: Optional[str]) -> Optional[float]:
    if amount is None or not currency:
        return None
    rate = FX_USD.get((currency or "").upper())
    if not rate:
        return None
    try:
        return round(float(amount) * rate, 2)
    except Exception:
        return None

def _clean_text(htmlish: Optional[str]) -> str:
    if not htmlish:
        return ""
    # strip tags
    txt = re.sub(r"<.*?>", " ", htmlish, flags=re.S)
    # collapse spaces
    return re.sub(r"\s+", " ", txt).strip()

# ====================================================================
# SKY­WALKER.GR (LIVE RSS)
# ====================================================================
async def fetch_skywalker() -> List[Dict[str, Any]]:
    """Live RSS feed from Skywalker.gr"""
    url = "https://www.skywalker.gr/jobs/feed"
    items: List[Dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url)
        r.raise_for_status()
        root = ET.fromstring(r.text)

    for it in root.findall(".//item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        desc = _clean_text(it.findtext("description"))
        pub = it.findtext("pubDate") or ""

        # Try parse RFC822-ish dates safely (fallback to None)
        posted = None
        try:
            # Example: Thu, 09 Oct 2025 13:12:45 +0300
            # We take first 25 chars to avoid tz parse issues and set UTC
            posted = datetime.strptime(pub[:25], "%a, %d %b %Y %H:%M:%S").replace(tzinfo=timezone.utc)
        except Exception:
            posted = None

        if not title or not link:
            continue

        items.append({
            "platform": "Skywalker",
            "title": title,
            "description": desc,
            "original_url": link,
            "affiliate_url": None,  # no affiliate
            "source_url": url,
            "country": "GR",
            "budget_amount": None,
            "budget_currency": None,
            "posted_at": posted,
            "hash": _hash_for(title, link),
        })
    return items

# ====================================================================
# FREELANCER.COM (PUBLIC LISTINGS SCRAPE)
# - No API key required. Parses the public /jobs page (recent projects).
# - Wraps links with AFFILIATE_PREFIX (you provided).
# - Best-effort HTML parsing; if layout changes, function gracefully returns [].
# ====================================================================
_FREELANCER_LIST_URL = "https://www.freelancer.com/jobs"

_JOB_CARD_RE = re.compile(
    r'<a[^>]+href="(?P<href>/projects/[^"]+)"[^>]*>\s*(?P<title>[^<]{5,200})</a>.*?'
    r'(?P<snippet><p[^>]*>.*?</p>)',
    re.S | re.I
)

def _wrap_affiliate(url: str) -> str:
    # Your affiliate wrapper
    return f"{AFFILIATE_PREFIX}{quote_plus(url)}" if AFFILIATE_PREFIX else url

async def fetch_freelancer() -> List[Dict[str, Any]]:
    """
    Fetch recent jobs from freelancer.com/jobs.
    NOTE: Lightweight regex parser — avoids extra deps and keeps setup stable.
    If parsing fails (layout change), returns [] without crashing the worker.
    """
    items: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (compatible; FreelancerAlertBot/1.0)"
        }) as client:
            r = await client.get(_FREELANCER_LIST_URL)
            r.raise_for_status()
            html = r.text
    except Exception:
        return items  # silent fail for robustness

    # Find up to ~50 cards
    for m in _JOB_CARD_RE.finditer(html):
        rel = m.group("href").strip()
        title = (m.group("title") or "").strip()
        snippet_html = m.group("snippet") or ""
        desc = _clean_text(snippet_html)

        if not rel or not title:
            continue

        orig = "https://www.freelancer.com" + rel
        aff = _wrap_affiliate(orig)

        items.append({
            "platform": "Freelancer",
            "title": title,
            "description": desc,
            "original_url": orig,
            "affiliate_url": aff,
            "source_url": _FREELANCER_LIST_URL,
            "country": None,
            "budget_amount": None,
            "budget_currency": None,
            "posted_at": None,
            "hash": _hash_for(title, orig),
        })

        if len(items) >= 50:
            break

    return items

# ====================================================================
# CAREERJET (placeholder active) — implement later with their search/RSS
# KARIERA (placeholder active) — requires access/format
# OTHER GLOBAL PLATFORMS — placeholders to keep pipeline on
# ====================================================================
async def fetch_careerjet() -> List[Dict[str, Any]]:
    return []

async def fetch_kariera() -> List[Dict[str, Any]]:
    return []

async def fetch_peopleperhour() -> List[Dict[str, Any]]: return []
async def fetch_malt() -> List[Dict[str, Any]]: return []
async def fetch_workana() -> List[Dict[str, Any]]: return []
async def fetch_wripple() -> List[Dict[str, Any]]: return []
async def fetch_toptal() -> List[Dict[str, Any]]: return []
async def fetch_twago() -> List[Dict[str, Any]]: return []
async def fetch_freelancermap() -> List[Dict[str, Any]]: return []
async def fetch_yunojuno() -> List[Dict[str, Any]]: return []
async def fetch_worksome() -> List[Dict[str, Any]]: return []
async def fetch_codeable() -> List[Dict[str, Any]]: return []
async def fetch_guru() -> List[Dict[str, Any]]: return []
async def fetch_99designs() -> List[Dict[str, Any]]: return []

# Registry exported to worker
ALL_FETCHERS = [
    fetch_skywalker,
    fetch_freelancer,   # now live
    fetch_careerjet,
    fetch_kariera,
    fetch_peopleperhour,
    fetch_malt,
    fetch_workana,
    fetch_wripple,
    fetch_toptal,
    fetch_twago,
    fetch_freelancermap,
    fetch_yunojuno,
    fetch_worksome,
    fetch_codeable,
    fetch_guru,
    fetch_99designs,
]
