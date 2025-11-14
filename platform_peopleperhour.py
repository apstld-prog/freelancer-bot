# platform_peopleperhour.py — PeoplePerHour collector (RSS + SPA fallback) with 429 handling
# - Tiered sources: RSS search -> Generic RSS -> SPA search-page
# - Robust HTTP client: persistent session, retries, exponential backoff, Retry-After support
# - Pacing between pages to avoid CloudFront 429
# - 48h filter, matched_keyword, FX rates, interval 120s
# - No UI changes

from typing import List, Dict, Optional, Tuple
import os, re, html, urllib.parse, logging, json, time, random
from datetime import datetime, timezone, timedelta
import httpx

log = logging.getLogger("pph")

# ---------------- ENV ----------------
FRESH_HOURS = int(os.getenv("PPH_FRESH_HOURS", os.getenv("FRESH_WINDOW_HOURS", "48")))
PPH_BASE_URL = os.getenv("PPH_BASE_URL", "https://www.peopleperhour.com/freelance-jobs?rss=1&search={kw}")
PPH_MAX_PAGES = int(os.getenv("PPH_MAX_PAGES", "10"))
PPH_REQUEST_TIMEOUT = float(os.getenv("PPH_REQUEST_TIMEOUT", "15"))
PPH_INTERVAL_SECONDS = int(os.getenv("PPH_INTERVAL_SECONDS", "120"))
PPH_SEND_ALL = os.getenv("PPH_SEND_ALL", "1") == "1"
PPH_PER_KEYWORD_LIMIT = int(os.getenv("PPH_MAX_ITEMS_PER_TICK", "200"))
PPH_SLEEP_BETWEEN_PAGES = float(os.getenv("PPH_SLEEP_BETWEEN_PAGES", "0.6"))
HTTP_RETRIES = int(os.getenv("HTTP_RETRIES", "3"))
HTTP_BACKOFF = float(os.getenv("HTTP_BACKOFF", "1.6"))
FX_RATES = json.loads(os.getenv("FX_RATES", '{"USD":1.0,"EUR":1.08,"GBP":1.26}'))
DEBUG_LOG = os.getenv("PER_KEYWORD_DEBUG", "0") == "1" or os.getenv("LOG_LEVEL", "").upper() == "DEBUG"

# ---------------- HTTP session with backoff ----------------
_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36",
]

def _client():
    headers = {
        "User-Agent": random.choice(_UAS),
        "Accept": "text/html,application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": "https://www.peopleperhour.com/",
    }
    return httpx.Client(headers=headers, timeout=PPH_REQUEST_TIMEOUT, follow_redirects=True, http2=False)

def _http_get(url: str) -> Optional[httpx.Response]:
    with _client() as c:
        delay = 0.05 + random.random() * 0.1
        time.sleep(delay)
        last_exc = None
        for attempt in range(1, HTTP_RETRIES + 1):
            try:
                r = c.get(url)
                # 429/503 handling
                if r.status_code in (429, 503):
                    ra = r.headers.get("Retry-After")
                    wait = float(ra) if (ra and ra.isdigit()) else (HTTP_BACKOFF ** attempt) + random.random()
                    if DEBUG_LOG:
                        log.warning(f"[PPH] {r.status_code} on {url} — retry {attempt}/{HTTP_RETRIES} after {wait:.2f}s")
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                return r
            except Exception as e:
                last_exc = e
                wait = (HTTP_BACKOFF ** attempt) + random.random() * 0.5
                if DEBUG_LOG:
                    log.debug(f"[PPH] GET failed ({type(e).__name__}) attempt {attempt}/{HTTP_RETRIES} — backoff {wait:.2f}s")
                time.sleep(wait)
        if DEBUG_LOG:
            log.warning(f"[PPH] GET gave up: {url} ({last_exc})")
        return None

def _fetch(url: str) -> str:
    r = _http_get(url)
    if not r:
        raise httpx.HTTPError(f"GET failed after retries: {url}")
    return r.text

# ---------------- Currency helpers ----------------
_CURRENCY_MAP = {"£":"GBP","€":"EUR","$":"USD","C$":"CAD","A$":"AUD","₹":"INR","NZ$":"NZD","CHF":"CHF"}
_SYM_ORDER = sorted(_CURRENCY_MAP.keys(), key=len, reverse=True)

def _convert_currency(amount: Optional[float], code: Optional[str]) -> Optional[str]:
    if amount is None or not code:
        return None
    try:
        code = code.upper()
        rates = FX_RATES or {}
        usd = amount if code == "USD" else (amount / rates.get(code, 1.0))
        eur = usd * rates.get("EUR", 1.0)
        return f"{amount:.0f} {code} (~${usd:.0f} USD / €{eur:.0f} EUR)"
    except Exception:
        return f"{amount:.0f} {code}"

# ---------------- Helpers ----------------
def _strip_html(s: str) -> str:
    try:
        text = re.sub(r"<[^>]+>", " ", s or "", flags=re.S | re.I)
        return html.unescape(re.sub(r"\s+", " ", text)).strip()
    except Exception:
        return (s or "").strip()

def _match_keyword(title: str, description: str, keywords: List[str]) -> Optional[str]:
    hay = f"{(title or '').lower()}\n{(description or '').lower()}"
    for kw in keywords or []:
        k = (kw or "").strip().lower()
        if k and k in hay:
            return kw
    return None

def _parse_rss_datetime(s: str) -> Optional[datetime]:
    if not s: return None
    s = s.strip()
    fmts = [
        "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M:%S",
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(s.replace("GMT","+0000"), fmt)
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
            else: dt = dt.astimezone(timezone.utc)
            return dt
        except Exception:
            continue
    return None

# ---------------- RSS parsing ----------------
_RE_ITEM = re.compile(r"<item\b.*?>.*?</item>", re.S | re.I)
_RE_TITLE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.S | re.I)
_RE_LINK = re.compile(r"<link\b[^>]*>(.*?)</link>", re.S | re.I)
_RE_DESC = re.compile(r"<description\b[^>]*>(.*?)</description>", re.S | re.I)
_RE_DATE = re.compile(r"<pubDate\b[^>]*>(.*?)</pubDate>", re.S | re.I)

def _parse_rss_items(body: str) -> List[Dict]:
    out = []
    for blk in _RE_ITEM.findall(body) or []:
        title = _strip_html(_RE_TITLE.search(blk).group(1)) if _RE_TITLE.search(blk) else ""
        link = _strip_html(_RE_LINK.search(blk).group(1)) if _RE_LINK.search(blk) else ""
        desc_raw = _RE_DESC.search(blk).group(1) if _RE_DESC.search(blk) else ""
        desc = _strip_html(desc_raw)
        pub_s = _RE_DATE.search(blk).group(1) if _RE_DATE.search(blk) else ""
        dt = _parse_rss_datetime(pub_s) or datetime.now(timezone.utc)
        if link and link.startswith("/"):
            link = "https://www.peopleperhour.com" + link
        out.append({"rss_title": title, "rss_desc": desc, "rss_link": link, "rss_date": dt})
    return out

def _rss_search(keyword: str, page: int) -> List[Dict]:
    base = PPH_BASE_URL.replace("{kw}", urllib.parse.quote_plus(keyword))
    url = base if "{page}" in base else f"{base}{'&' if '?' in base else '?'}page={page}"
    body = _fetch(url)
    items = _parse_rss_items(body)
    if DEBUG_LOG:
        log.log(logging.INFO if items else logging.DEBUG, f"[PPH] RSS(search) p{page} kw={keyword}: {len(items)} items")
    return items

def _generic_rss_base() -> str:
    base = PPH_BASE_URL
    if "rss=1" not in base:
        base = "https://www.peopleperhour.com/freelance-jobs?rss=1"
    base = re.sub(r"[&?]search=\{?kw\}?","", base)
    base = re.sub(r"[?&]$", "", base)
    return base

GENERIC_RSS_BASE = _generic_rss_base()

def _rss_generic(page: int) -> List[Dict]:
    base = GENERIC_RSS_BASE
    url = base if "{page}" in base else f"{base}{'&' if '?' in base else '?'}page={page}"
    body = _fetch(url)
    items = _parse_rss_items(body)
    if DEBUG_LOG:
        log.info(f"[PPH] RSS(generic) p{page}: {len(items)} items")
    return items

# ---------------- SPA search-page fallback ----------------
# Capture both legacy /job/<id>-slug and modern /freelance-jobs/.../<slug>-<id>
_RE_JOB_URL = re.compile(
    r'/(?:job/\d+(?:-[a-z0-9\-%_]+)?|freelance-jobs/[a-z0-9\-/]+-[0-9]{5,})',
    re.I
)

def _spa_search_urls(keyword: str, page: int) -> List[str]:
    url = f"https://www.peopleperhour.com/freelance-jobs?q={urllib.parse.quote_plus(keyword)}&page={page}"
    body = _fetch(url)
    urls = []
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
        if len(urls) >= 300:
            break
    if DEBUG_LOG:
        log.info(f"[PPH] SPA search p{page} kw={keyword}: extracted {len(urls)} job URLs")
    return urls

# ---------------- HTML details (job page) ----------------
def _parse_json_ld(html_text: str) -> Dict:
    for m in re.finditer(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html_text, re.S | re.I):
        try:
            data = json.loads(m.group(1))
            if isinstance(data, dict): return data
            if isinstance(data, list) and data: return data[0]
        except Exception:
            continue
    return {}

def _extract_budget(text: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    t = text or ""
    for sym in _SYM_ORDER:
        sym_esc = re.escape(sym)
        m = re.search(rf"{sym_esc}\s*(\d+(?:[\.,]\d+)?)\s*[-–]\s*{sym_esc}?\s*(\d+(?:[\.,]\d+)?)", t)
        if m:
            a = float(m.group(1).replace(",", ".")); b = float(m.group(2).replace(",", "."))
            return (min(a, b), max(a, b), _CURRENCY_MAP.get(sym, sym))
        m2 = re.search(rf"{sym_esc}\s*(\d+(?:[\.,]\d+)?)\b", t)
        if m2:
            v = float(m2.group(1).replace(",", "."))
            return (v, v, _CURRENCY_MAP.get(sym, sym))
    m3 = re.search(r"\b(GBP|EUR|USD|CAD|AUD|INR|NZD|CHF)\s*(\d+(?:[\.,]\d+)?)", t, re.I)
    if m3:
        code = m3.group(1).upper(); v = float(m3.group(2).replace(",", "."))
        return (v, v, code)
    return (None, None, None)

def _fetch_job_details(url: str) -> Dict:
    body = _fetch(url)

    # Title
    title = None
    m = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.I | re.S)
    if m: title = _strip_html(m.group(1))
    if not title:
        m2 = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
        title = _strip_html(m2.group(1)) if m2 else "Untitled"

    # Description
    desc = ""
    data = _parse_json_ld(body)
    if isinstance(data, dict):
        for key in ("description", "about"):
            v = data.get(key)
            if isinstance(v, str) and len(v) > 20:
                desc = _strip_html(v); break
    if not desc:
        m3 = re.search(r'<div[^>]+class="[^"]*(?:job-description|description|jobDesc)[^"]*"[^>]*>(.*?)</div>',
                       body, re.I | re.S)
        if m3: desc = _strip_html(m3.group(1))
    if not desc:
        m4 = re.search(r"Description</[^>]+>(.{60,800})<", body, re.I | re.S)
        if m4: desc = _strip_html(m4.group(1))
    desc = (desc or "").strip()
    if len(desc) > 900: desc = desc[:900] + "…"

    # Budget
    budget_min = budget_max = None; currency = None
    if isinstance(data, dict):
        val = data.get("estimatedSalary") or data.get("salary")
        if isinstance(val, dict):
            try:
                budget_min = float(val.get("value", {}).get("minValue"))
                budget_max = float(val.get("value", {}).get("maxValue"))
                currency = val.get("currency")
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
                if s.endswith("Z"): s = s.replace("Z", "+00:00")
                dt = datetime.fromisoformat(s).astimezone(timezone.utc); break
            except Exception:
                pass
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
        item["currency"] = currency.upper()
        item["currency_display"] = item["currency"]
        if budget_min is not None:
            item["budget_display"] = _convert_currency(budget_min, item["currency"])
    return item

# ---------------- Public API ----------------
def get_items(keywords: List[str]) -> List[Dict]:
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
                items = []
            if not items:
                if page == 1 and DEBUG_LOG:
                    log.debug(f"[PPH] RSS: no items on page {page} for '{kw}'")
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
            urls = []
            for page in range(1, PPH_MAX_PAGES + 1):
                try:
                    urls.extend(_spa_search_urls(kw, page))
                except Exception as e:
                    log.debug(f"[PPH] SPA search page error p{page} kw={kw}: {e}")
                if len(urls) >= PPH_PER_KEYWORD_LIMIT:
                    break
                time.sleep(PPH_SLEEP_BETWEEN_PAGES + random.random()*0.4)
            search_items = [{"rss_link": u, "rss_date": datetime.now(timezone.utc)} for u in urls]
            if DEBUG_LOG:
                log.info(f"[PPH] SPA search gathered {len(urls)} URLs for kw={kw}")

        # Enrich + filter by age + keyword
        count_before = len(all_items)
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
                jdt = datetime.strptime(job["date"], "%a, %d %b %Y %H:%M:%S %z")
            except Exception:
                jdt = datetime.now(timezone.utc)
            if jdt < cutoff:
                continue
            mk = _match_keyword(job.get("title",""), job.get("description",""), [kw])
            if not mk and not PPH_SEND_ALL:
                continue
            job["matched_keyword"] = mk or kw
            if "budget_display" not in job and job.get("budget_min") and job.get("currency"):
                job["budget_display"] = _convert_currency(job["budget_min"], job["currency"])
            all_items.append(job)
            if len(all_items) - count_before >= PPH_PER_KEYWORD_LIMIT:
                break

        if DEBUG_LOG:
            log.info(f"[PPH] kw={kw} +{len(all_items)-count_before} items (total {len(all_items)})"
                     + (" [generic]" if using_generic else "") + (" [spa]" if using_spa else ""))

    # De-dup
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
