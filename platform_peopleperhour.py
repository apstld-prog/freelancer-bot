
# platform_peopleperhour.py
from __future__ import annotations

import re
import os
import json
import datetime as dt
from typing import List, Dict, Any, Optional

import httpx

USER_AGENT = os.getenv("HTTP_USER_AGENT", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "15"))
PPH_BASE = "https://www.peopleperhour.com"

def _log(logger, msg: str):
    if logger:
        try: logger.debug(msg)
        except Exception: pass

def _client():
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, follow_redirects=True)

def _http_get(url: str, logger=None) -> Optional[str]:
    try:
        with _client() as c:
            r = c.get(url)
        _log(logger, f"PPH GET {url} -> {r.status_code} {r.headers.get('Content-Type')}")
        if r.status_code == 200:
            return r.text
    except Exception as e:
        _log(logger, f"PPH GET error: {e}")
    return None

_job_href_re = re.compile(r'href="(/job/\d+[^"]*)"')
_meta_og_re = re.compile(r'<meta\s+property="og:(title|description)"\s+content="([^"]*)"', re.I)
_budget_json_re = re.compile(r'"budget"\s*:\s*\{[^}]*"amount"\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*,\s*"currency"\s*:\s*"([A-Z]{3})"', re.I)
_budget_text_re = re.compile(r'(?:(USD|GBP|EUR|CAD|AUD|INR|AED|SAR|TRY|PLN|CHF|SEK|NOK|DKK|RON|BGN|HUF|CZK|ZAR|BRL|ARS|MXN|JPY|CNY|HKD|SGD|NZD|RUB|\£|\€|\$)\s?)([0-9][0-9\.,]*)')
_datetime_iso_re = re.compile(r'"createdAt"\s*:\s*"([^"]+)"')

def _extract_jobs_from_search_html(html: str, logger=None) -> list[dict]:
    hrefs = _job_href_re.findall(html or "")
    hrefs = list(dict.fromkeys(hrefs))
    items = []
    for href in hrefs[:100]:
        url = PPH_BASE + href.split('"',1)[0]
        items.append({"url": url})
    _log(logger, f"PPH: found {len(items)} job links on search page")
    return items

def _parse_job_detail(html: str) -> dict:
    title = None
    desc = None
    created_iso = None
    for k, v in _meta_og_re.findall(html or ""):
        if k.lower() == "title": title = v.strip()
        elif k.lower() == "description": desc = v.strip()
    m = _budget_json_re.search(html or "")
    currency = None
    amount = None
    if m:
        amount = float(m.group(1))
        currency = m.group(2)
    else:
        mt = _budget_text_re.search(html or "")
        if mt:
            cur = mt.group(1)
            if cur in ("£",): currency = "GBP"
            elif cur in ("€",): currency = "EUR"
            elif cur in ("$",): currency = "USD"
            else: currency = cur
            num = mt.group(2).replace(",", "")
            try: amount = float(num)
            except: amount = None
    dm = _datetime_iso_re.search(html or "")
    if dm: created_iso = dm.group(1)
    return {"title": title, "description": desc, "budget": amount, "currency": currency, "created_iso": created_iso}

def _parse_iso_or_now(s: Optional[str]) -> dt.datetime:
    if not s: return dt.datetime.utcnow()
    try:
        return dt.datetime.fromisoformat(s.replace("Z","+00:00")).astimezone(dt.timezone.utc).replace(tzinfo=None)
    except Exception:
        return dt.datetime.utcnow()

def _kw_ok(text: str, keywords: list[str]) -> bool:
    if not keywords: return True
    T = (text or "").lower()
    return any(kw.lower() in T for kw in keywords)

def _fetch_search_pages(keywords: list[str], logger=None) -> list[dict]:
    items = []
    seen = set()
    for kw in keywords or []:
        q = httpx.QueryParams({"search": kw})
        url = f"{PPH_BASE}/freelance-jobs?{q}"
        html = _http_get(url, logger)
        if not html: continue
        for it in _extract_jobs_from_search_html(html, logger):
            if it["url"] in seen: continue
            seen.add(it["url"])
            items.append(it)
    return items

def get_items(*, keywords: list[str], fresh_since: dt.datetime, limit: int = 30, logger=None) -> List[Dict[str, Any]]:
    logger and logger.debug("PPH:get_items start")
    candidates = _fetch_search_pages(keywords, logger)
    out: List[Dict[str, Any]] = []
    for it in candidates:
        if len(out) >= max(1, int(limit)): break
        html = _http_get(it["url"], logger)
        if not html: continue
        details = _parse_job_detail(html)
        title = details.get("title") or ""
        desc = details.get("description") or ""
        if not _kw_ok(title + " " + desc, keywords): continue
        m = re.search(r'/job/(\d+)', it["url"])
        job_id = m.group(1) if m else str(abs(hash(it["url"])))
        created = _parse_iso_or_now(details.get("created_iso"))
        if created < fresh_since: continue
        out.append({
            "id": f"pph-{job_id}",
            "title": title or "(no title)",
            "url": it["url"],
            "description": desc or "",
            "budget": details.get("budget"),
            "currency": details.get("currency"),
            "source": "peopleperhour",
            "created_at": created,
        })
    logger and logger.info(f"peopleperhour fetched={len(out)}")
    return out
