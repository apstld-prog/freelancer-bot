
import os
import re
import json
import math
import html
import httpx
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Iterable, Optional
from urllib.parse import urlencode, urljoin, urlparse, parse_qs

USER_AGENT = os.getenv("HTTP_USER_AGENT", "Mozilla/5.0 (X11; Linux x86_64) PeoplePerHourBot/1.0")
DEFAULT_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "15"))
DEFAULT_LIMIT = int(os.getenv("FETCH_LIMIT", "200"))

PPH_BASE = "https://www.peopleperhour.com"
PPH_SEARCH_PATH = "/freelance-jobs"
PPH_RSS_QS = {"rss": "1"}

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _to_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def _parse_http_date(val: str) -> Optional[datetime]:
    try:
        # Example RSS pubDate: 'Sun, 19 Oct 2025 09:38:25 GMT'
        from email.utils import parsedate_to_datetime
        d = parsedate_to_datetime(val)
        return _to_utc(d.astimezone(timezone.utc))
    except Exception:
        return None

def _strip_tags(s: str) -> str:
    # basic tag stripper
    return re.sub(r"<[^>]+>", " ", s or "").replace("\xa0"," ").strip()

def _findall_jsonld(html_text: str) -> Iterable[dict]:
    # Grab all <script type="application/ld+json"> blocks
    for m in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html_text, flags=re.I|re.S):
        raw = html.unescape(m.group(1)).strip()
        if not raw:
            continue
        # Many sites wrap multiple JSONs or have dangling commas; try best-effort
        candidates = []
        try:
            j = json.loads(raw)
            candidates = j if isinstance(j, list) else [j]
        except Exception:
            # try to repair common issues: remove trailing commas
            fixed = re.sub(r",\s*([}\]])", r"\1", raw)
            try:
                j = json.loads(fixed)
                candidates = j if isinstance(j, list) else [j]
            except Exception:
                continue
        for obj in candidates:
            if isinstance(obj, dict):
                yield obj

def _extract_price_fields(obj: dict) -> (Optional[float], Optional[str], Optional[bool]):
    # Supports either "offers":{price,priceCurrency} or "estimatedSalary":{...} or nested
    amount = None
    currency = None
    hourly = None

    offers = obj.get("offers")
    if isinstance(offers, dict):
        amount = _safe_float(offers.get("price"))
        currency = offers.get("priceCurrency") or offers.get("currency")
        hourly = (offers.get("@type") == "UnitPriceSpecification" and str(offers.get("unitText", "")).lower().startswith("hour"))
    elif isinstance(offers, list) and offers:
        for off in offers:
            if isinstance(off, dict) and ("price" in off or "priceCurrency" in off):
                amount = _safe_float(off.get("price"))
                currency = off.get("priceCurrency") or off.get("currency")
                hourly = (off.get("@type") == "UnitPriceSpecification" and str(off.get("unitText", "")).lower().startswith("hour"))
                break

    est = obj.get("estimatedSalary")
    if amount is None and isinstance(est, dict):
        amount = _safe_float(est.get("value") or est.get("minValue") or est.get("maxValue"))
        currency = currency or est.get("currency")
        hourly = hourly or (str(est.get("unitText", "")).lower().startswith("hour"))

    if isinstance(amount, (int, float)):
        # sanitize extremely large/invalid values
        if not math.isfinite(float(amount)) or float(amount) < 0:
            amount = None

    if isinstance(currency, str):
        currency = currency.upper().strip()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            # Try symbol mapping
            symmap = {"$":"USD","£":"GBP","€":"EUR"}
            if currency in symmap:
                currency = symmap[currency]
            else:
                currency = None

    return amount, currency, hourly

def _safe_float(v) -> Optional[float]:
    try:
        return float(str(v).replace(",", "").strip())
    except Exception:
        return None

def _normalize_item(raw: Dict[str, Any]) -> Dict[str, Any]:
    # Normalize final dict fields to align with freelancer format used by the bot
    return {
        "platform": "peopleperhour",
        "id": raw.get("id") or raw.get("url"),
        "title": raw.get("title"),
        "url": raw.get("url"),
        "description": raw.get("description"),
        "posted_at": raw.get("posted_at"),  # ISO8601
        "budget_amount": raw.get("budget_amount"),
        "budget_currency": raw.get("budget_currency"),
        "is_hourly": raw.get("is_hourly", False),
        "source": "pph",
    }

def _fetch(client: httpx.Client, url: str, logger=None) -> Optional[str]:
    try:
        resp = client.get(url, headers={"User-Agent": USER_AGENT}, timeout=DEFAULT_TIMEOUT)
        if logger:
            logger.info(f"PPH GET {url} -> {resp.status_code}")
        if resp.status_code == 200:
            return resp.text
    except Exception as e:
        if logger:
            logger.warning(f"PPH GET failed {url}: {e}")
    return None

def _rss_items(xml_text: str) -> Iterable[Dict[str, Any]]:
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml_text)
        # RSS namespaces can vary; search generically
        for it in root.iter():
            if it.tag.lower().endswith("item"):
                d = {child.tag.split("}")[-1].lower(): (child.text or "") for child in it}
                title = html.unescape(d.get("title","")).strip()
                link = (d.get("link") or "").strip()
                desc = html.unescape(d.get("description","")).strip()
                pub = _parse_http_date(d.get("pubdate","")) or _now_utc()
                # try budget from desc
                cur = None; amt = None; hourly = None
                m = re.search(r"([£€$])\s?(\d+(?:[.,]\d{1,2})?)", desc)
                if m:
                    sym = m.group(1)
                    amt = _safe_float(m.group(2))
                    cur = {"£":"GBP","€":"EUR","$":"USD"}.get(sym, None)
                yield {
                    "title": title,
                    "url": link if link else None,
                    "description": _strip_tags(desc),
                    "posted_at": pub.astimezone(timezone.utc).isoformat(),
                    "budget_amount": amt,
                    "budget_currency": cur,
                    "is_hourly": bool(hourly),
                }
    except Exception:
        return []

def _html_items(html_text: str) -> Iterable[Dict[str, Any]]:
    # Prefer JSON-LD JobPosting entries
    out = []
    for obj in _findall_jsonld(html_text):
        typ = (obj.get("@type") or "").lower()
        if typ not in ("jobposting", "creativework", "article", "newsarticle"):
            # Collections may hold {"@graph":[...]} or similar
            graph = obj.get("@graph")
            if isinstance(graph, list):
                for node in graph:
                    if isinstance(node, dict) and (node.get("@type","").lower() in ("jobposting","creativework")):
                        out.append(_obj_to_item(node))
                continue
            # otherwise skip
            continue
        out.append(_obj_to_item(obj))
    # Deduplicate by URL
    seen = set()
    final = []
    for it in out:
        url = it.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        final.append(it)
    return final

def _obj_to_item(obj: dict) -> Dict[str, Any]:
    title = obj.get("title") or obj.get("name") or ""
    url = obj.get("url") or ""
    desc = obj.get("description") or ""
    date = obj.get("datePosted") or obj.get("datePublished") or obj.get("dateCreated") or ""
    posted = None
    if date:
        try:
            posted = datetime.fromisoformat(date.replace("Z","+00:00"))
        except Exception:
            posted = _now_utc()
    else:
        posted = _now_utc()

    amt, cur, hourly = _extract_price_fields(obj)

    return {
        "title": _strip_tags(html.unescape(title)),
        "url": urljoin(PPH_BASE, url) if url and url.startswith("/") else url,
        "description": _strip_tags(html.unescape(desc)),
        "posted_at": _to_utc(posted).isoformat(),
        "budget_amount": amt,
        "budget_currency": cur,
        "is_hourly": bool(hourly),
    }

def _match_keywords(text: str, keywords: Iterable[str]) -> bool:
    if not keywords:
        return True
    s = (text or "").lower()
    for kw in keywords:
        if not kw:
            continue
        if kw.lower() in s:
            return True
    return False

def get_items(keywords: Optional[List[str]] = None,
              fresh_since: Optional[datetime] = None,
              limit: Optional[int] = None,
              logger: Optional[Any] = None) -> List[Dict[str, Any]]:
    """
    Main entry expected by worker_runner.
    - keywords: list of keyword strings (already split). Can be None/[] to fetch all.
    - fresh_since: UTC datetime; only include items newer than this.
    - limit: max items to return (defaults to env FETCH_LIMIT or 200).
    - logger: optional logger.
    Returns: list of normalized dicts.
    """
    lim = int(limit or DEFAULT_LIMIT)
    fresh_since = _to_utc(fresh_since) if fresh_since else (_now_utc() - timedelta(hours=int(os.getenv("FRESH_WINDOW_HOURS","48"))))

    results: List[Dict[str, Any]] = []
    kw_list = [k.strip() for k in (keywords or []) if k and k.strip()]
    kw_list = kw_list or []

    # If no keywords were passed, try to derive from env KEYWORDS (comma separated).
    if not kw_list:
        env_kw = os.getenv("KEYWORDS", "")
        if env_kw:
            kw_list = [x.strip() for x in env_kw.split(",") if x.strip()]

    # Always search at least once (no keywords -> broad search page to harvest items)
    search_terms = kw_list or [""]

    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    with httpx.Client(headers=headers, timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
        for term in search_terms:
            # 1) Try RSS first
            qs = dict(PPH_RSS_QS)
            if term:
                qs["search"] = term
            rss_url = f"{PPH_BASE}{PPH_SEARCH_PATH}?{urlencode(qs)}"
            xml_text = _fetch(client, rss_url, logger=logger)
            rss_items = list(_rss_items(xml_text)) if xml_text else []

            # 2) If RSS empty, fallback to HTML (JSON-LD)
            html_items = []
            if not rss_items:
                qs2 = {"search": term} if term else {}
                html_url = f"{PPH_BASE}{PPH_SEARCH_PATH}?{urlencode(qs2)}" if qs2 else f"{PPH_BASE}{PPH_SEARCH_PATH}"
                html_text2 = _fetch(client, html_url, logger=logger)
                if html_text2:
                    html_items = list(_html_items(html_text2))

            raw_items = rss_items or html_items

            # Filter & normalize
            for it in raw_items:
                try:
                    title = (it.get("title") or "").strip()
                    desc = (it.get("description") or "").strip()
                    url = (it.get("url") or "").strip()
                    posted_at = it.get("posted_at")
                    dt = None
                    if isinstance(posted_at, str):
                        try:
                            dt = datetime.fromisoformat(posted_at.replace("Z","+00:00"))
                        except Exception:
                            dt = _now_utc()
                    elif isinstance(posted_at, datetime):
                        dt = _to_utc(posted_at)
                    else:
                        dt = _now_utc()

                    if dt < fresh_since:
                        continue

                    text_blob = f"{title}\n{desc}"
                    if kw_list and not _match_keywords(text_blob, kw_list):
                        continue

                    norm = _normalize_item({
                        "id": url,
                        "title": title,
                        "url": url,
                        "description": desc,
                        "posted_at": _to_utc(dt).isoformat(),
                        "budget_amount": it.get("budget_amount"),
                        "budget_currency": it.get("budget_currency"),
                        "is_hourly": it.get("is_hourly", False),
                    })
                    results.append(norm)
                except Exception:
                    continue

            # stop if we reached limit
            if len(results) >= lim:
                break

    # Sort by posted_at desc and trim to limit
    def _key(x):
        try:
            return datetime.fromisoformat(x["posted_at"].replace("Z","+00:00"))
        except Exception:
            return _now_utc()
    results.sort(key=_key, reverse=True)
    if len(results) > lim:
        results = results[:lim]

    # Ensure unique by URL
    seen = set()
    uniq = []
    for r in results:
        u = r.get("url")
        if u and u not in seen:
            seen.add(u)
            uniq.append(r)
    return uniq
