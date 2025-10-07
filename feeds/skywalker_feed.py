# feeds/skywalker_feed.py
# -*- coding: utf-8 -*-
"""
Skywalker RSS fetcher (https://www.skywalker.gr/jobs/feed)
- Async fetch with httpx
- XML parsing with ElementTree
- NO pre-filtering by keywords (let the worker filter per user)
- Returns cards compatible with worker schema
"""

from __future__ import annotations

import os
import re
import html
from typing import List, Dict, Optional
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from xml.etree import ElementTree as ET
from email.utils import parsedate_to_datetime

SKY_FEED_URL = os.getenv("SKY_FEED_URL", "https://www.skywalker.gr/jobs/feed").strip()
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "20"))

def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def _extract_id_from_link(link: str) -> str:
    if not link:
        return "sky-unknown"
    m = re.search(r"/aggelia/(\d+)", link)
    if m:
        return f"sky-{m.group(1)}"
    path = urlparse(link).path or link
    tid = re.sub(r"[^a-zA-Z0-9]", "", path)[-16:]
    return f"sky-{tid or 'x'}"

def _safe_dt(dt: Optional[datetime]) -> str:
    if not dt:
        return "recent"
    try:
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return "recent"

async def fetch_skywalker_feed(_: List[str] | None = None) -> List[Dict]:
    """
    Fetch all items from the RSS (no keyword filtering here).
    Worker will filter per-user using title+description.
    """
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"}) as client:
            r = await client.get(SKY_FEED_URL)
            if r.status_code != 200:
                return []
            xml = r.text
    except Exception:
        return []

    try:
        root = ET.fromstring(xml)
    except Exception:
        return []

    channel = root.find("channel") or root.find("{*}channel")
    if channel is None:
        return []

    cards: List[Dict] = []
    items = channel.findall("item") + channel.findall("{*}item")
    for item in items:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc_raw = item.findtext("description") or ""
        pub = item.findtext("pubDate") or item.findtext("{*}pubDate") or ""

        desc = _strip_html(desc_raw)

        jid = _extract_id_from_link(link)

        dt = None
        if pub:
            try:
                dt = parsedate_to_datetime(pub)
            except Exception:
                dt = None

        cards.append({
            "id": jid,
            "source": "Skywalker",
            "title": title or "Untitled",
            "type": None,
            "budget_local": "—",
            "budget_usd": None,
            "bids": None,
            "posted": _safe_dt(dt),
            "description": (desc or "")[:500],
            "proposal_url": link,
            "original_url": link,
        })

    return cards
