# -*- coding: utf-8 -*-
"""
PeoplePerHour scraper (HTML search, no RSS).

Public API expected by worker_runner.py:
    get_items(keywords: list[str], fresh_since: datetime|None, limit: int|None, logger) -> list[dict]
Returns a list of standardized job dicts:
    {
        "id": str,                 # stable unique id
        "title": str,
        "url": str,
        "source": "peopleperhour",
        "posted_at": datetime|None,
        "budget": {"amount": float|None, "currency": str|None, "type": str|None},
        "description": str|None
    }

Behavior:
- Paginates search results per keyword (?page=N) until either:
  * reaches items older than PPH_FRESH_HOURS (default 48h) OR
  * hits PPH_MAX_PAGES (default 10) OR
  * hits PPH_MAX_ITEMS_PER_TICK (default 200) OR
  * satisfies 'limit' if provided by the worker.
- Robust HTML parsing without external libs (regex + minimal heuristics).
- Attempts to parse “posted” age from common text fragments (“hour(s) ago”, “day(s) ago”).
- Defensive against HTML/CSS changes — best-effort extraction.
"""

from __future__ import annotations
import os, re, time
from html import unescape
from urllib.parse import urlencode, urljoin
from datetime import datetime, timedelta, timezone
import httpx

BASE = "https://www.peopleperhour.com"
SEARCH_PATH = "/freelance-jobs"

# -------- Settings (env tunables) --------
PPH_FRESH_HOURS = int(os.getenv("PPH_FRESH_HOURS", "48"))
PPH_MAX_PAGES = int(os.getenv("PPH_MAX_PAGES", "10"))
PPH_MAX_ITEMS_PER_TICK = int(os.getenv("PPH_MAX_ITEMS_PER_TICK", "200"))
PPH_REQUEST_TIMEOUT = float(os.getenv("PPH_REQUEST_TIMEOUT", "15"))
PPH_SLEEP_BETWEEN_PAGES = float(os.getenv("PPH_SLEEP_BETWEEN_PAGES", "0"))
PPH_USER_AGENT = os.getenv("PPH_USER_AGENT", "Mozilla/5.0 (compatible; PPHBot/1.0; +https://example.com)")

FRESH_DELTA = timedelta(hours=PPH_FRESH_HOURS)

# Regexes for scraping
RE_JOB_CARD = re.compile(r'<a[^>]+href="(?P<href>/freelance-jobs/[^"#?]+)"[^>]*>(?P<title>.*?)</a>', re.I | re.S)
# Budget examples: "£100", "$25/hr", "€200 — Fixed Price", etc.
RE_BUDGET = re.compile(r'(?:(?:£|\$|€)\s?\d+(?:[.,]\d{1,2})?)\s*(?:/hr|per hour|fixed|fixed price|hourly)?', re.I)
# Relative age examples: "Posted 3 hours ago", "1 day ago"
RE_AGE = re.compile(r'(?:(?:posted|updated)\s*)?(\d+)\s*(minute|hour|day|week|month)s?\s*ago', re.I)
# Job id slug & numeric id in URL if present
RE_ID = re.compile(r'/freelance-jobs/([^"/?#]+)')

def _debug(logger, msg: str):
    try:
        logger.debug(msg)
    except Exception:
        pass

def _info(logger, msg: str):
    try:
        logger.info(msg)
    except Exception:
        pass

def _now():
    return datetime.now(timezone.utc)

def _fetch_html(url: str, logger) -> str | None:
    headers = {"User-Agent": PPH_USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    try:
        with httpx.Client(timeout=PPH_REQUEST_TIMEOUT, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
            _info(logger, f"PPH GET {url} status={resp.status_code}")
            if resp.status_code == 200 and resp.text:
                return resp.text
    except Exception as e:
        _debug(logger, f"PPH fetch error {url}: {e}")
    return None

def _parse_age(text: str) -> datetime | None:
    """
    Return UTC datetime for a relative 'ago' string if found; else None.
    """
    m = RE_AGE.search(text)
    if not m:
        return None
    qty = int(m.group(1))
    unit = m.group(2).lower()
    delta = None
    if unit.startswith("minute"):
        delta = timedelta(minutes=qty)
    elif unit.startswith("hour"):
        delta = timedelta(hours=qty)
    elif unit.startswith("day"):
        delta = timedelta(days=qty)
    elif unit.startswith("week"):
        delta = timedelta(weeks=qty)
    elif unit.startswith("month"):
        # Approximate a month as 30 days
        delta = timedelta(days=30*qty)
    if delta is None:
        return None
    return _now() - delta

def _extract_cards(html: str, logger) -> list[dict]:
    """
    Best-effort extraction of job anchors + nearby context to pull budget / age.
    """
    items = []
    for m in RE_JOB_CARD.finditer(html):
        href = unescape(m.group("href"))
        title = unescape(re.sub(r"<[^>]+>", "", m.group("title"))).strip()
        url = urljoin(BASE, href)

        # Local context window around the anchor to sniff budget/age
        start, end = max(0, m.start()-800), min(len(html), m.end()+800)
        ctx = html[start:end]

        # Budget
        budget_match = RE_BUDGET.search(ctx)
        budget_text = budget_match.group(0) if budget_match else None
        currency = None
        amount = None
        btype = None
        if budget_text:
            bt = budget_text.replace(",", "").strip()
            if bt.startswith("£"):
                currency = "GBP"
                bt_num = bt[1:]
            elif bt.startswith("$"):
                currency = "USD"
                bt_num = bt[1:]
            elif bt.startswith("€"):
                currency = "EUR"
                bt_num = bt[1:]
            else:
                bt_num = bt
            # Type
            if "/hr" in bt.lower() or "hour" in bt.lower():
                btype = "hourly"
            elif "fixed" in bt.lower():
                btype = "fixed"
            # Number
            mnum = re.search(r'(\d+(?:\.\d{1,2})?)', bt_num)
            if mnum:
                try:
                    amount = float(mnum.group(1))
                except Exception:
                    amount = None

        # Age
        posted_at = _parse_age(ctx)

        # ID
        id_match = RE_ID.search(href)
        pid = id_match.group(1) if id_match else href.strip("/").replace("/", "_")

        items.append({
            "id": pid,
            "title": title or "Untitled",
            "url": url,
            "source": "peopleperhour",
            "posted_at": posted_at,
            "budget": {"amount": amount, "currency": currency, "type": btype},
            "description": None,  # detail fetch optional later
        })
    return items

def _is_fresh(dt: datetime | None, fresh_since: datetime | None) -> bool:
    if fresh_since and dt:
        return dt >= fresh_since
    if dt:
        return dt >= (_now() - FRESH_DELTA)
    # If no timestamp, treat as unknown-fresh -> keep but will be capped by max items
    return True

def _dedupe_keep_latest(items: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for it in items:
        key = it.get("id") or it.get("url")
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out

def get_items(*, keywords: list[str] | None = None, fresh_since: datetime | None = None,
              limit: int | None = None, logger=None) -> list[dict]:
    """
    Main entry. See module docstring.
    """
    logger = logger or type("L", (), {"debug": print, "info": print})()
    if not keywords:
        # If no keywords, just do a broad page 1 to avoid heavy crawl
        keywords = [""]

    total_cap = min(PPH_MAX_ITEMS_PER_TICK, limit or PPH_MAX_ITEMS_PER_TICK)
    all_items: list[dict] = []
    for kw in keywords:
        kw = (kw or "").strip()
        pages_scanned = 0
        page = 1
        while page <= PPH_MAX_PAGES and len(all_items) < total_cap:
            qs = {"search": kw} if kw else {}
            if page > 1:
                qs["page"] = page
            url = f"{BASE}{SEARCH_PATH}"
            if qs:
                url = f"{url}?{urlencode(qs)}"

            html = _fetch_html(url, logger)
            if not html:
                break

            cards = _extract_cards(html, logger)
            if not cards:
                # no more results
                break

            # freshness filter
            fresh = [it for it in cards if _is_fresh(it.get("posted_at"), fresh_since)]
            # If all cards are stale (and we have timestamps), we can stop early
            if not fresh and any(it.get("posted_at") is not None for it in cards):
                break

            all_items.extend(fresh or cards)  # keep unknown-age if none fresh

            pages_scanned += 1
            if len(all_items) >= total_cap:
                break

            if PPH_SLEEP_BETWEEN_PAGES > 0:
                time.sleep(PPH_SLEEP_BETWEEN_PAGES)
            page += 1

    all_items = _dedupe_keep_latest(all_items)
    # Trim to 'limit' if provided
    if limit is not None and len(all_items) > limit:
        all_items = all_items[:limit]

    _info(logger, f"peopleperhour fetched={len(all_items)} (cap={total_cap}, pages<= {PPH_MAX_PAGES})")
    return all_items
