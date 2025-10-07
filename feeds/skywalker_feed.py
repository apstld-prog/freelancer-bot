# feeds/skywalker_feed.py
# -*- coding: utf-8 -*-
"""
Skywalker RSS fetcher (https://www.skywalker.gr/jobs/feed)
- Ασύγχρονο fetch με httpx (χωρίς εξτρά βιβλιοθήκες RSS)
- XML parsing με ElementTree
- Keyword filtering σε title+description, ascii/tonos-insensitive
- Επιστρέφει κάρτες στο ίδιο σχήμα με τον worker (id/source/title/description/proposal_url/original_url/...).
"""

from __future__ import annotations

import os
import re
import html
import unicodedata
from typing import List, Dict, Optional
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from xml.etree import ElementTree as ET
from email.utils import parsedate_to_datetime

# ---- Config (με ασφαλή defaults) ----
SKY_FEED_URL = os.getenv("SKY_FEED_URL", "https://www.skywalker.gr/jobs/feed").strip()
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "20"))

# ---- Utilities ----

def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    # remove tags
    text = re.sub(r"<[^>]+>", " ", text)
    # collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text

def _norm(s: str) -> str:
    """
    Lowercase + remove diacritics (τόνοι) + keep alnum/space for loose matching.
    """
    s = (s or "").lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"[^a-z0-9\u0370-\u03FF\s]+", " ", s)  # κρατά λατινικά + ελληνικά γράμματα + spaces
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _match_any(text: str, keywords: List[str]) -> bool:
    if not keywords:
        return True  # αν δεν δώσουμε keywords, επέστρεψε όλα (συνήθως δεν το θέλουμε)
    t = _norm(text)
    for kw in keywords:
        if not kw:
            continue
        if _norm(kw) and _norm(kw) in t:
            return True
    return False

def _extract_id_from_link(link: str) -> str:
    """
    Προσπαθεί να βγάλει σταθερό id από το URL τύπου:
      https://www.skywalker.gr/elGR/aggelia/XXXXX
    Αν δεν βρεθεί, χρησιμοποιεί hash-like fallback.
    """
    if not link:
        return "sky-unknown"
    m = re.search(r"/aggelia/(\d+)", link)
    if m:
        return f"sky-{m.group(1)}"
    # fallback: last 16 alnum chars from URL path
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

# ---- Core fetcher ----

async def fetch_skywalker_feed(keywords: List[str]) -> List[Dict]:
    """
    Τραβά το RSS, κάνει parse τα items και φιλτράρει με βάση τα keywords
    (σε τίτλο + περιγραφή). Επιστρέφει κάρτες ίδιες με του worker.
    """
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"}) as client:
            r = await client.get(SKY_FEED_URL)
            if r.status_code != 200:
                # Αν πέσει προσωρινά, γύρνα κενό (ο worker είναι ανθεκτικός)
                return []
            xml = r.text
    except Exception:
        return []

    try:
        root = ET.fromstring(xml)
    except Exception:
        return []

    # RSS 2.0: <rss><channel><item>...</item></channel></rss>
    channel = root.find("channel")
    if channel is None:
        # κάποιες υλοποιήσεις έχουν namespaces, δοκίμασε ελαστικά
        channel = root.find("{*}channel")
        if channel is None:
            return []

    cards: List[Dict] = []
    for item in channel.findall("item") + channel.findall("{*}item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc_raw = item.findtext("description") or ""
        pub = item.findtext("pubDate") or item.findtext("{*}pubDate") or ""

        desc = _strip_html(desc_raw)

        # keyword filter σε title+description
        haystack = f"{title} {desc}"
        if not _match_any(haystack, keywords):
            continue

        jid = _extract_id_from_link(link)

        # parse pubDate -> ISO
        dt = None
        if pub:
            try:
                dt = parsedate_to_datetime(pub)
            except Exception:
                dt = None

        card = {
            "id": jid,
            "source": "Skywalker",
            "title": title or "Untitled",
            "type": None,
            "budget_local": "—",
            "budget_usd": None,
            "bids": None,
            "posted": _safe_dt(dt),     # ISO UTC ή "recent"
            "description": desc[:500],  # κόψε για Telegram preview
            "proposal_url": link,       # δεν υπάρχει affiliate εδώ
            "original_url": link,
        }
        cards.append(card)

    return cards
