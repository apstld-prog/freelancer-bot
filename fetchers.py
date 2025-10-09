# fetchers.py — platform adapters (Skywalker live + placeholders), USD conversion
from __future__ import annotations
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import httpx

from db_events import _hash_for

AFFILIATE_PREFIX = "https://www.freelancer.com/get/apstld?f=give&dl="  # keep as provided

# Simple FX table (placeholder). Extend with real rates if needed.
FX_USD = {
    "USD": 1.0, "EUR": 1.08, "GBP": 1.26, "PLN": 0.25, "RON": 0.22, "HUF": 0.0027,
}

def to_usd(amount: Optional[float], currency: Optional[str]) -> Optional[float]:
    if amount is None or not currency:
        return None
    rate = FX_USD.get(currency.upper())
    if not rate: return None
    try:
        return round(float(amount) * rate, 2)
    except Exception:
        return None

def _clean_text(htmlish: Optional[str]) -> str:
    if not htmlish: return ""
    txt = re.sub(r"<.*?>", " ", htmlish, flags=re.S)
    return re.sub(r"\s+", " ", txt).strip()

# ---------------- Skywalker.gr (RSS) ----------------
async def fetch_skywalker() -> List[Dict[str, Any]]:
    url = "https://www.skywalker.gr/jobs/feed"
    items: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url)
        r.raise_for_status()
        root = ET.fromstring(r.text)

    # RSS namespace-agnostic
    for it in root.findall(".//item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        desc = _clean_text(it.findtext("description"))
        pub = it.findtext("pubDate") or ""
        try:
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

# ---------------- Careerjet.gr (placeholder) ----------------
async def fetch_careerjet() -> List[Dict[str, Any]]:
    # Placeholder active: returns empty list but keeps the pipeline alive.
    # If later you add their RSS/search, implement here.
    return []

# ---------------- Global freelance platforms (placeholders) ----------------
async def fetch_freelancer() -> List[Dict[str, Any]]:
    # TODO: replace with real API/RSS. Placeholder demonstrates affiliate wrapping.
    # Return empty to avoid noise until you wire actual API.
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

# Registry
ALL_FETCHERS = [
    fetch_skywalker,
    fetch_careerjet,
    fetch_freelancer,
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
