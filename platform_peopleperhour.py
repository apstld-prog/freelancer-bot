# platform_peopleperhour.py — PeoplePerHour collector (RSS + SPA fallback)
# This is the "old" working version, adapted to your current worker pipeline:
# - Adds time_submitted (epoch seconds)
# - Normalizes fields: source, url, original_url, proposal_url, original_currency, affiliate
#
# NOTE: It still respects ENABLE_PPH and P_PEOPLEPERHOUR env flags. 

import os
import re
import json
import time
import random
import logging
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple

import httpx

log = logging.getLogger("platform_peopleperhour")

# ---------------- Config ----------------

PPH_BASE_URL = os.getenv(
    "PPH_BASE_URL",
    "https://www.peopleperhour.com/freelance-jobs?rss=1&search={kw}",
)

PPH_GENERIC_URL = os.getenv(
    "PPH_GENERIC_URL",
    "https://www.peopleperhour.com/freelance-jobs?rss=1&page={page}",
)

PPH_SPA_URL = os.getenv(
    "PPH_SPA_URL",
    "https://www.peopleperhour.com/freelance-jobs?q={kw}&page={page}",
)

FRESH_HOURS = int(os.getenv("PPH_FRESH_HOURS", "72"))
PPH_MAX_PAGES = int(os.getenv("PPH_MAX_PAGES", "3"))
PPH_PER_KEYWORD_LIMIT = int(os.getenv("PPH_PER_KEYWORD_LIMIT", "40"))
PPH_SEND_ALL = os.getenv("PPH_SEND_ALL", "0") in ("1", "true", "True")
PPH_SLEEP_BETWEEN_PAGES = float(os.getenv("PPH_SLEEP_BETWEEN_PAGES", "0.8"))
TIMEOUT = float(os.getenv("PPH_HTTP_TIMEOUT", "15.0"))

DEBUG_LOG = os.getenv("PPH_DEBUG_LOG", "0") in ("1", "true", "True")

FX_RATES_PATH = os.getenv("FX_USD_RATES", "")
FX_RATES: Dict[str, float] = {}

# common currencies
_CURRENCY_MAP = {
    "$": "USD", "£": "GBP", "€": "EUR", "₹": "INR", "A$": "AUD", "C$": "CAD",
    "R$": "BRL", "CHF": "CHF",
}
_SYM_ORDER = ["£", "€", "$", "A$", "C$", "R$", "₹"]  # more common first

RSS_JOB_RE = re.compile(
    r"<item>(.*?)</item>",
    re.I | re.S
)
RSS_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.I | re.S)
RSS_LINK_RE = re.compile(r"<link>(.*?)</link>", re.I | re.S)
RSS_DESC_RE = re.compile(r"<description>(.*?)</description>", re.I | re.S)
RSS_DATE_RE = re.compile(r"<pubDate>(.*?)</pubDate>", re.I | re.S)

_RE_JOB_URL = re.compile(
    r"/freelance-jobs/[a-z0-9\-/]+-[0-9]{5,}",
    re.I
)


# ---------------- HTTP helpers ----------------

def _load_fx() -> None:
    global FX_RATES
    if FX_RATES or not FX_RATES_PATH:
        return
    try:
        import json
        with open(FX_RATES_PATH, "r", encoding="utf-8") as f:
            FX_RATES = json.load(f)
    except Exception:
        FX_RATES = {}


def _ua() -> str:
    uas = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/117.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    ]
    return random.choice(uas)


def _http_get(url: str) -> str:
    if DEBUG_LOG:
        log.info(f"[PPH] GET {url}")
    headers = {
        "User-Agent": _ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "close",
    }
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
        r = client.get(url, headers=headers)
        r.raise_for_status()
        return r.text


def _fetch(url: str) -> str:
    try:
        return _http_get(url)
    except Exception as e:
        log.warning(f"[PPH] HTTP error: {e} url={url}")
        raise


# ---------------- Parsing helpers ----------------

def _strip_html(s: str) -> str:
    try:
        text = re.sub(r"<[^>]+>", " ", s or "", flags=re.S | re.I)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
    except Exception:
        return s or ""


def _match_keyword(title: str, description: str, keywords: List[str]) -> Optional[str]:
    hay = f"{(title or '').lower()}\n{(description or '').lower()}"
    for kw in keywords or []:
        k = (kw or "").strip().lower()
        if k and k in hay:
            return kw
    return None


def _parse_rss_datetime(s: str) -> Optional[datetime]:
    if not s:
        return None
    s = s.strip()
    fmts = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%d %b %Y %H:%M:%S %z",
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _parse_rss_items(body: str) -> List[Dict]:
    out: List[Dict] = []
    for m in RSS_JOB_RE.finditer(body or ""):
        block = m.group(1)
        title_m = RSS_TITLE_RE.search(block)
        link_m = RSS_LINK_RE.search(block)
        desc_m = RSS_DESC_RE.search(block)
        date_m = RSS_DATE_RE.search(block)
        title = _strip_html(title_m.group(1)) if title_m else ""
        link = (link_m.group(1).strip() if link_m else "").replace("&amp;", "&")
        desc = _strip_html(desc_m.group(1)) if desc_m else ""
        date_raw = date_m.group(1).strip() if date_m else ""
        out.append({
            "rss_title": title,
            "rss_link": link,
            "rss_desc": desc,
            "rss_date": date_raw,
        })
    return out


def _extract_budget(text: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    t = text or ""
    for sym in _SYM_ORDER:
        sym_esc = re.escape(sym)
        m = re.search(rf"{sym_esc}\s*(\d+(?:[\.,]\d+)?)\s*[-–]\s*{sym_esc}?\s*(\d+(?:[\.,]\d+)?)", t)
        if m:
            a = float(m.group(1).replace(",", "."))
            b = float(m.group(2).replace(",", "."))
            return (min(a, b), max(a, b), _CURRENCY_MAP.get(sym, sym))
        m2 = re.search(rf"{sym_esc}\s*(\d+(?:[\.,]\d+)?)\b", t)
        if m2:
            v = float(m2.group(1).replace(",", "."))
            return (v, v, _CURRENCY_MAP.get(sym, sym))
    m3 = re.search(r"\b(GBP|EUR|USD|CAD|AUD|INR|NZD|CHF)\s*(\d+(?:[\.,]\d+)?)", t, re.I)
    if m3:
        code = m3.group(1).upper()
        v = float(m3.group(2).replace(",", "."))
        return (v, v, code)
    return (None, None, None)


def _parse_json_ld(body: str):
    try:
        for m in re.finditer(r"<script[^>]+type=\"application/ld\+json\"[^>]*>(.*?)</script>", body, re.I | re.S):
            raw = m.group(1).strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except Exception:
                continue
            return data
    except Exception:
        return None
    return None


def _convert_currency(amount: Optional[float], code: Optional[str]) -> Optional[str]:
    if amount is None or not code:
        return None
    try:
        code = code.upper()
        _load_fx()
        rates = FX_RATES or {}
        usd = amount if code == "USD" else (amount / rates.get(code, 1.0))
        eur = usd * rates.get("EUR", 1.0)
        return f"{amount:.0f} {code} (~${usd:.0f} USD / €{eur:.0f} EUR)"
    except Exception:
        return f"{amount:.0f} {code}"


# ---------------- Job detail fetch ----------------

def _fetch_job_details(url: str) -> Dict:
    body = _fetch(url)

    # Title
    title = None
    m = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.I | re.S)
    if m:
        title = _strip_html(m.group(1))
    if not title:
        m2 = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
        title = _strip_html(m2.group(1)) if m2 else "Untitled"

    # Description
    desc = ""
    data = _parse_json_ld(body)
    if isinstance(data, dict):
        for key in ("description", "about"):
            if isinstance(data.get(key), str):
                desc = _strip_html(data[key])
                break
    if not desc:
        m3 = re.search(r"<div[^>]+class=\"[^\">]*job-description[^\">]*\"[^>]*>(.*?)</div>", body, re.I | re.S)
        if m3:
            desc = _strip_html(m3.group(1))

    # Budget
    budget_min = budget_max = None
    currency = None

    if isinstance(data, dict):
        # Try JSON-LD fields first
        amt = data.get("baseSalary") or data.get("estimatedSalary")
        if isinstance(amt, dict):
            try:
                val = amt.get("value", {})
                if isinstance(val, dict):
                    # min/max or single
                    if "minValue" in val and "maxValue" in val:
                        budget_min = float(val["minValue"])
                        budget_max = float(val["maxValue"])
                    elif "value" in val:
                        budget_min = budget_max = float(val["value"])
                    currency = val.get("currency") or currency
            except Exception:
                pass

    if budget_min is None and budget_max is None:
        budget_min, budget_max, currency = _extract_budget(body)

    # Date
    dt = None
    for key in ("datePosted", "datePublished", "uploadDate"):
        if isinstance(data, dict) and data.get(key):
            try:
                s = str(data[key])
                if s.endswith("Z"):
                    s = s.replace("Z", "+00:00")
                dt = datetime.fromisoformat(s).astimezone(timezone.utc)
                break
            except Exception:
                pass
    if not dt:
        dt = datetime.now(timezone.utc)

    item: Dict = {
        "title": title or "Untitled",
        "description": desc,
        "url": url,
        "original_url": url,
        "source": "peopleperhour",
        "date": dt.strftime("%a, %d %b %Y %H:%M:%S %z"),
        # 🔥 για το worker: epoch seconds, όπως ο freelancer
        "time_submitted": int(dt.timestamp()),
    }
    if budget_min is not None:
        item["budget_min"] = budget_min
    if budget_max is not None:
        item["budget_max"] = budget_max
    if currency:
        item["currency"] = currency.upper()
    return item


# ---------------- RSS fetchers ----------------

def _rss_search(keyword: str, page: int) -> List[Dict]:
    url = PPH_BASE_URL.format(kw=urllib.parse.quote_plus(keyword))
    if page > 1:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}page={page}"
    body = _fetch(url)
    return _parse_rss_items(body)


def _rss_generic(page: int) -> List[Dict]:
    url = PPH_GENERIC_URL.format(page=page)
    body = _fetch(url)
    return _parse_rss_items(body)


def _spa_search_urls(keyword: str, page: int) -> List[str]:
    url = PPH_SPA_URL.format(kw=urllib.parse.quote_plus(keyword), page=page)
    body = _fetch(url)
    urls: List[str] = []
    seen = set()
    for m in _RE_JOB_URL.finditer(body):
        path = m.group(0)
        full = "https://www.peopleperhour.com" + path
        if "/freelance-jobs/" in path and not re.search(r"-\d{5,}$", path):
            continue
        if full in seen:
            continue
        seen.add(full)
        urls.append(full)
    return urls


# ---------------- Public API ----------------

def get_items(keywords: List[str]) -> List[Dict]:
    # Env flags (όπως πριν)
    if not (os.getenv("ENABLE_PPH", "1") in ("1", "true", "True") and
            os.getenv("P_PEOPLEPERHOUR", "1") in ("1", "true", "True")):
        return []

    kw_list = [k.strip() for k in (keywords or []) if k and k.strip()]
    if not kw_list:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=FRESH_HOURS)
    all_items: List[Dict] = []

    for kw in kw_list:
        search_items: List[Dict] = []

        # 1) RSS search
        for page in range(1, PPH_MAX_PAGES + 1):
            try:
                items = _rss_search(kw, page)
            except Exception as e:
                log.warning(f"[PPH] RSS(search) fetch error kw={kw} p={page}: {e}")
                break
            if not items:
                break
            search_items.extend(items)
            if len(search_items) >= PPH_PER_KEYWORD_LIMIT:
                break
            time.sleep(PPH_SLEEP_BETWEEN_PAGES)

        using_generic = False
        if not search_items:
            # 2) Generic RSS fallback
            using_generic = True
            generic_items: List[Dict] = []
            for page in range(1, PPH_MAX_PAGES + 1):
                try:
                    items = _rss_generic(page)
                except Exception as e:
                    log.warning(f"[PPH] RSS(generic) fetch error p={page}: {e}")
                    break
                if not items:
                    break
                generic_items.extend(items)
                if len(generic_items) >= PPH_PER_KEYWORD_LIMIT:
                    break
                time.sleep(PPH_SLEEP_BETWEEN_PAGES)
            lowered_kw = kw.lower()
            search_items = [
                it for it in generic_items
                if lowered_kw in (it["rss_title"] or "").lower() or lowered_kw in (it["rss_desc"] or "").lower()
            ]
            if DEBUG_LOG:
                log.info(f"[PPH] Fallback generic RSS matched {len(search_items)} for kw={kw}")

        using_spa = False
        if not search_items:
            # 3) SPA search-page fallback
            using_spa = True
            urls: List[str] = []
            for page in range(1, PPH_MAX_PAGES + 1):
                try:
                    urls_page = _spa_search_urls(kw, page)
                except Exception as e:
                    log.warning(f"[PPH] SPA search error kw={kw} p={page}: {e}")
                    break
                if not urls_page:
                    break
                urls.extend(urls_page)
                if len(urls) >= PPH_PER_KEYWORD_LIMIT:
                    break
                time.sleep(PPH_SLEEP_BETWEEN_PAGES)

            for u in urls:
                try:
                    job = _fetch_job_details(u)
                except Exception as e:
                    log.debug(f"[PPH] SPA job fetch error {u}: {e}")
                    continue

                jdt = datetime.now(timezone.utc)
                try:
                    # We added time_submitted already
                    j_epoch = job.get("time_submitted")
                    if j_epoch:
                        jdt = datetime.fromtimestamp(int(j_epoch), tz=timezone.utc)
                except Exception:
                    pass
                if jdt < cutoff:
                    continue

                mk = _match_keyword(job.get("title", ""), job.get("description", ""), [kw])
                if not mk and not PPH_SEND_ALL:
                    continue

                job["matched_keyword"] = mk or kw
                # normalize structure for worker pipeline (freelancer-like)
                url = job.get("url") or job.get("original_url")
                if url:
                    job.setdefault("original_url", url)
                    job.setdefault("url", url)
                    job.setdefault("proposal_url", url)
                cur = job.get("currency")
                if cur and "original_currency" not in job:
                    job["original_currency"] = cur
                job.setdefault("affiliate", False)

                if "budget_display" not in job and job.get("budget_min") and job.get("currency"):
                    job["budget_display"] = _convert_currency(job["budget_min"], job["currency"])
                all_items.append(job)
                if len(all_items) >= PPH_PER_KEYWORD_LIMIT:
                    break

        count_before = len(all_items)

        # 4) For RSS items, fetch full job pages
        for r in search_items:
            link = r.get("rss_link") or ""
            if not link:
                continue
            try:
                job = _fetch_job_details(link)
            except Exception as e:
                log.debug(f"[PPH] job fetch error {link}: {e}")
                continue
            try:
                jdt = _parse_rss_datetime(r.get("rss_date") or "") or datetime.now(timezone.utc)
            except Exception:
                jdt = datetime.now(timezone.utc)
            if jdt < cutoff:
                continue
            mk = _match_keyword(job.get("title", ""), job.get("description", ""), [kw])
            if not mk and not PPH_SEND_ALL:
                continue

            job["matched_keyword"] = mk or kw
            # normalize structure for worker pipeline (freelancer-like)
            url = job.get("url") or job.get("original_url")
            if url:
                job.setdefault("original_url", url)
                job.setdefault("url", url)
                job.setdefault("proposal_url", url)
            cur = job.get("currency")
            if cur and "original_currency" not in job:
                job["original_currency"] = cur
            job.setdefault("affiliate", False)

            if "budget_display" not in job and job.get("budget_min") and job.get("currency"):
                job["budget_display"] = _convert_currency(job["budget_min"], job["currency"])
            all_items.append(job)
            if len(all_items) - count_before >= PPH_PER_KEYWORD_LIMIT:
                break

        if DEBUG_LOG:
            log.info(
                f"[PPH] kw={kw} +{len(all_items) - count_before} items (total {len(all_items)})"
                + (" [generic]" if using_generic else "")
                + (" [spa]" if using_spa else "")
            )

    # De-dup (per URL)
    seen, uniq = set(), []
    for it in all_items:
        key = (it.get("url") or it.get("original_url") or "").strip()
        if not key:
            key = f"pph::{(it.get('title') or '')[:160]}"
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)

    if DEBUG_LOG:
        log.info(f"[PPH] Total {len(uniq)} jobs collected for {len(kw_list)} keywords")

    return uniq
