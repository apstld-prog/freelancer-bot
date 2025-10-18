# platform_peopleperhour.py — pph_sitemap_v1
from typing import List, Dict, Optional, Tuple
import os, re, html, json, urllib.parse, logging
from datetime import datetime, timezone, timedelta
import httpx
import xml.etree.ElementTree as ET

log = logging.getLogger("pph")

FRESH_HOURS = int(os.getenv("FRESH_WINDOW_HOURS", "48"))
USER_AGENT = os.getenv("HTTP_USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 JobBot/pph_sitemap_v1")
PPH_SEND_ALL = os.getenv("PPH_SEND_ALL", "0") == "1"
PPH_PER_RUN_LIMIT = int(os.getenv("PPH_SITEMAP_LIMIT", "40"))
PPH_SITEMAP_URL = os.getenv("PPH_SITEMAP_URL", "https://www.peopleperhour.com/sitemap_jobs.xml")

_CURRENCY_MAP = {"£":"GBP","€":"EUR","$":"USD","C$":"CAD","A$":"AUD","₹":"INR","NZ$":"NZD","CHF":"CHF"}
_SYM_ORDER = sorted(_CURRENCY_MAP.keys(), key=len, reverse=True)

def _http_get(url: str, timeout: float = 20.0) -> str:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.peopleperhour.com/",
    }
    r = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    return r.text

def _to_dt_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def _parse_lastmod(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    s = s.strip()
    try:
        if s.endswith("Z"):
            s = s.replace("Z", "+00:00")
        return _to_dt_aware(datetime.fromisoformat(s))
    except Exception:
        pass
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            return _to_dt_aware(datetime.strptime(s, fmt))
        except Exception:
            pass
    return None

def _strip_html(s: str) -> str:
    try:
        text = re.sub(r"<[^>]+>", " ", s or "", flags=re.S|re.I)
        return html.unescape(re.sub(r"\s+", " ", text)).strip()
    except Exception:
        return (s or "").strip()

def _extract_budget(text: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    t = text or ""
    for sym in _SYM_ORDER:
        sym_esc = re.escape(sym)
        m = re.search(rf"{sym_esc}\s*(\d+(?:[\.,]\d+)?)\s*[-–]\s*{sym_esc}?\s*(\d+(?:[\.,]\d+)?)", t)
        if m:
            a = float(m.group(1).replace(",", ".")); b = float(m.group(2).replace(",", "."))
            return (min(a,b), max(a,b), _CURRENCY_MAP.get(sym, sym))
        m2 = re.search(rf"{sym_esc}\s*(\d+(?:[\.,]\d+)?)\b", t)
        if m2:
            v = float(m2.group(1).replace(",", "."))
            return (v, v, _CURRENCY_MAP.get(sym, sym))
    m3 = re.search(r"\b(GBP|EUR|USD|CAD|AUD|INR|NZD|CHF)\s*(\d+(?:[\.,]\d+)?)", t, re.I)
    if m3:
        code = m3.group(1).upper(); v = float(m3.group(2).replace(",", "."))
        return (v, v, code)
    return (None, None, None)

def _parse_json_ld(html_text: str) -> Dict:
    for m in re.finditer(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html_text, re.S|re.I):
        try:
            data = json.loads(m.group(1))
            if isinstance(data, dict): return data
            if isinstance(data, list) and data: return data[0]
        except Exception:
            continue
    return {}

def _fetch_job_details(url: str) -> Dict:
    try:
        body = _http_get(url, timeout=20.0)
    except Exception as e:
        log.debug("PPH job fetch failed %s: %s", url, e)
        return {}

    title = None
    m = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.I|re.S)
    if m: title = _strip_html(m.group(1))
    if not title:
        m2 = re.search(r"<title[^>]*>(.*?)</title>", body, re.I|re.S)
        title = _strip_html(m2.group(1)) if m2 else ""

    desc = ""
    data = _parse_json_ld(body)
    if isinstance(data, dict):
        for key in ("description","jobLocation","about"):
            v = data.get(key)
            if isinstance(v, str) and len(v) > 20:
                desc = _strip_html(v); break
    if not desc:
        m3 = re.search(r'<div[^>]+class="[^"]*(?:job-description|description|jobDesc)[^"]*"[^>]*>(.*?)</div>', body, re.I|re.S)
        if m3: desc = _strip_html(m3.group(1))
    if not desc:
        m4 = re.search(r"Description</[^>]+>(.{60,800})<", body, re.I|re.S)
        if m4: desc = _strip_html(m4.group(1))
    desc = (desc or "").strip()
    if len(desc) > 900: desc = desc[:900] + "…"

    budget_min = budget_max = None; currency = None
    if isinstance(data, dict):
        val = data.get("estimatedSalary") or data.get("salary")
        if isinstance(val, dict):
            try:
                budget_min = float(val.get("value",{}).get("minValue"))
                budget_max = float(val.get("value",{}).get("maxValue"))
                currency = val.get("currency")
            except Exception:
                pass
    if budget_min is None and budget_max is None:
        budget_min, budget_max, currency = _extract_budget(body)

    dt = None
    for key in ("datePosted","datePublished","uploadDate"):
        if isinstance(data, dict) and data.get(key):
            try:
                s = str(data[key])
                if s.endswith("Z"): s = s.replace("Z","+00:00")
                dt = datetime.fromisoformat(s).astimezone(timezone.utc); break
            except Exception: pass
    if not dt:
        dt = datetime.now(timezone.utc)

    item = {
        "title": title or "Untitled",
        "description": desc,
        "url": url,
        "original_url": url,
        "source": "peopleperhour",
        "date": dt.strftime("%a, %d %b %Y %H:%M:%S %z"),
    }
    if budget_min is not None: item["budget_min"] = budget_min
    if budget_max is not None: item["budget_max"] = budget_max
    if currency:
        item["currency"] = currency
        item["currency_display"] = currency
    return item

def _keyword_match(s: str, keywords: List[str]) -> Optional[str]:
    L = (s or "").lower()
    for kw in keywords or []:
        k = (kw or "").strip().lower()
        if k and k in L:
            return kw
    return None

def _gather_from_sitemap(keywords: List[str]) -> List[Dict]:
    try:
        xml = _http_get(PPH_SITEMAP_URL, timeout=25.0)
    except Exception as e:
        log.warning("PPH sitemap fetch failed: %s", e)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=FRESH_HOURS)
    jobs = []  # (url, lastmod)

    try:
        root = ET.fromstring(xml)
    except Exception as e:
        log.warning("PPH sitemap parse failed: %s", e)
        return []

    if root.tag.endswith("sitemapindex"):
        for sm in root.findall(".//{*}sitemap"):
            loc = (sm.findtext("{*}loc") or "").strip()
            if not loc:
                continue
            try:
                sub = _http_get(loc, timeout=20.0)
                sub_root = ET.fromstring(sub)
                for u in sub_root.findall(".//{*}url"):
                    loc2 = (u.findtext("{*}loc") or "").strip()
                    lastmod = u.findtext("{*}lastmod")
                    dt = _parse_lastmod(lastmod)
                    if loc2 and "/job/" in loc2:
                        if not dt or dt >= cutoff:
                            jobs.append((loc2, dt))
            except Exception:
                continue
    else:
        for u in root.findall(".//{*}url"):
            loc = (u.findtext("{*}loc") or "").strip()
            lastmod = u.findtext("{*}lastmod")
            dt = _parse_lastmod(lastmod)
            if loc and "/job/" in loc:
                if not dt or dt >= cutoff:
                    jobs.append((loc, dt))

    jobs.sort(key=lambda x: x[1] or datetime(1970,1,1, tzinfo=timezone.utc), reverse=True)

    selected = []
    lowered_kws = [(kw or "").strip().lower() for kw in (keywords or []) if (kw or "").strip()]
    for url, _lm in jobs:
        slug = urllib.parse.unquote(url.lower())
        if lowered_kws and any(kw in slug for kw in lowered_kws):
            selected.append(url)
        elif PPH_SEND_ALL:
            selected.append(url)
        if len(selected) >= 200:
            break

    items = []
    for url in selected:
        it = _fetch_job_details(url)
        if not it:
            continue
        mk = None
        if lowered_kws:
            mk = _keyword_match(it.get("title",""), keywords) or _keyword_match(it.get("description",""), keywords)
        if mk or PPH_SEND_ALL:
            if mk:
                it["matched_keyword"] = mk
            items.append(it)
        if len(items) >= PPH_PER_RUN_LIMIT:
            break
    return items

def get_items(keywords: List[str]) -> List[Dict]:
    if not (os.getenv("ENABLE_PPH","0")=="1" and os.getenv("P_PEOPLEPERHOUR","0")=="1"):
        return []
    try:
        items = _gather_from_sitemap(keywords or [])
        log.info("PPH (sitemap) fetched=%d", len(items))
        return items
    except Exception as e:
        log.warning("PPH sitemap pipeline error: %s", e)
        return []
