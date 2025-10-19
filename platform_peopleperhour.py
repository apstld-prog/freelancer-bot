# platform_peopleperhour.py — PeoplePerHour: RSS discovery + HTML details
# - Fetch listings from PPH RSS search (server-side, paginated)
# - Enrich each job by scraping the job page HTML for title/desc/budget/date
# - Filter by last 48h, keyword match in title/description
# - Return unified items (same schema as Freelancer source)
# - No UI changes. Works with existing worker/runner.

from typing import List, Dict, Optional, Tuple
import os, re, html, urllib.parse, logging, json
from datetime import datetime, timezone, timedelta
import httpx

log = logging.getLogger("pph")

# ---------------- ENV ----------------
FRESH_HOURS = int(os.getenv("PPH_FRESH_HOURS", os.getenv("FRESH_WINDOW_HOURS", "48")))
USER_AGENT = os.getenv(
    "PPH_USER_AGENT",
    os.getenv(
        "HTTP_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 FreelancerBot/1.0"
    ),
)
PPH_BASE_URL = os.getenv(
    "PPH_BASE_URL",
    "https://www.peopleperhour.com/freelance-jobs?rss=1&search={kw}"
)
PPH_MAX_PAGES = int(os.getenv("PPH_MAX_PAGES", "10"))
PPH_REQUEST_TIMEOUT = float(os.getenv("PPH_REQUEST_TIMEOUT", "15"))
PPH_INTERVAL_SECONDS = int(os.getenv("PPH_INTERVAL_SECONDS", "120"))
PPH_SEND_ALL = os.getenv("PPH_SEND_ALL", "1") == "1"  # keep behavior from env (default ON per your env)
PPH_PER_KEYWORD_LIMIT = int(os.getenv("PPH_MAX_ITEMS_PER_TICK", "200"))
FX_RATES = json.loads(os.getenv("FX_RATES", '{"USD":1.0,"EUR":1.08,"GBP":1.26}'))
DEBUG_LOG = os.getenv("PER_KEYWORD_DEBUG", "0") == "1" or os.getenv("LOG_LEVEL", "").upper() == "DEBUG"

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

# ---------------- Generic helpers ----------------
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

def _fetch(url: str, timeout: float = None) -> str:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.peopleperhour.com/",
    }
    r = httpx.get(url, headers=headers, timeout=timeout or PPH_REQUEST_TIMEOUT, follow_redirects=True)
    r.raise_for_status()
    return r.text

# ---------------- RSS discovery (listing) ----------------
_RE_ITEM = re.compile(r"<item\b.*?>.*?</item>", re.S | re.I)
_RE_TITLE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.S | re.I)
_RE_LINK = re.compile(r"<link\b[^>]*>(.*?)</link>", re.S | re.I)
_RE_DESC = re.compile(r"<description\b[^>]*>(.*?)</description>", re.S | re.I)
_RE_DATE = re.compile(r"<pubDate\b[^>]*>(.*?)</pubDate>", re.S | re.I)

def _rss_items_for_keyword(keyword: str) -> List[Dict]:
    items: List[Dict] = []
    for page in range(1, PPH_MAX_PAGES + 1):
        base = PPH_BASE_URL.replace("{kw}", urllib.parse.quote_plus(keyword))
        url = base if "{page}" not in base else base.replace("{page}", str(page))
        if "{page}" not in base:
            # If base has no {page}, add &page=n
            sep = "&" if "?" in base else "?"
            url = f"{base}{sep}page={page}"
        try:
            body = _fetch(url)
        except Exception as e:
            log.warning(f"[PPH] RSS fetch failed (kw={keyword}, p={page}): {e}")
            continue

        blocks = _RE_ITEM.findall(body) or []
        if not blocks:
            # stop on empty page
            if DEBUG_LOG: log.debug(f"[PPH] RSS: no items on page {page} for '{keyword}'")
            break

        for blk in blocks:
            title = _strip_html(_RE_TITLE.search(blk).group(1)) if _RE_TITLE.search(blk) else ""
            link = _strip_html(_RE_LINK.search(blk).group(1)) if _RE_LINK.search(blk) else ""
            desc_raw = _RE_DESC.search(blk).group(1) if _RE_DESC.search(blk) else ""
            desc = _strip_html(desc_raw)
            pub_s = _RE_DATE.search(blk).group(1) if _RE_DATE.search(blk) else ""
            dt = _parse_rss_datetime(pub_s) or datetime.now(timezone.utc)

            # Normalize to job URL (sometimes link includes tracking or redirects)
            if link and link.startswith("/"):
                link = "https://www.peopleperhour.com" + link

            items.append({
                "rss_title": title,
                "rss_desc": desc,
                "rss_link": link,
                "rss_date": dt,
                "keyword": keyword,
            })

        if DEBUG_LOG:
            log.info(f"[PPH] RSS page {page}: +{len(blocks)} items (kw={keyword})")

        if len(items) >= PPH_PER_KEYWORD_LIMIT:
            break

    return items[:PPH_PER_KEYWORD_LIMIT]

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
    # Range like £100–200
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
    # Codes (USD 100)
    m3 = re.search(r"\b(GBP|EUR|USD|CAD|AUD|INR|NZD|CHF)\s*(\d+(?:[\.,]\d+)?)", t, re.I)
    if m3:
        code = m3.group(1).upper(); v = float(m3.group(2).replace(",", "."))
        return (v, v, code)
    return (None, None, None)

def _fetch_job_details(url: str) -> Dict:
    try:
        body = _fetch(url)
    except Exception as e:
        log.debug("PPH job fetch failed %s: %s", url, e)
        return {}

    # Title
    title = None
    m = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.I | re.S)
    if m: title = _strip_html(m.group(1))
    if not title:
        m2 = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
        title = _strip_html(m2.group(1)) if m2 else "Untitled"

    # Description (JSON-LD first)
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
        # Fallback: take a fair chunk after “Description”
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
        # Fallback to now; actual freshness is enforced by the RSS pubDate filter
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
        # pretty budget display if we have min
        if budget_min is not None:
            item["budget_display"] = _convert_currency(budget_min, item["currency"])
    return item

# ---------------- Public API ----------------
def get_items(keywords: List[str]) -> List[Dict]:
    # Respect toggles; if disabled, return empty
    if not (os.getenv("ENABLE_PPH", "1") in ("1", "true", "True") and
            os.getenv("P_PEOPLEPERHOUR", "1") in ("1", "true", "True")):
        return []

    kw_list = [k.strip() for k in (keywords or []) if k and k.strip()]
    if not kw_list:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=FRESH_HOURS)
    all_items: List[Dict] = []

    for kw in kw_list:
        rss_items = _rss_items_for_keyword(kw)
        if DEBUG_LOG:
            log.info(f"[PPH] RSS collected {len(rss_items)} items (kw={kw})")

        # Filter by age first (RSS pubDate is reliable)
        rss_items = [r for r in rss_items if r["rss_date"] >= cutoff]
        if DEBUG_LOG:
            log.info(f"[PPH] RSS filtered {len(rss_items)} items within {FRESH_HOURS}h (kw={kw})")

        # Enrich each RSS item by scraping the job page HTML
        count_before = len(all_items)
        for r in rss_items:
            link = r.get("rss_link") or ""
            if not link:
                continue
            job = _fetch_job_details(link)
            if not job:
                continue

            # Matched keyword check (title+desc)
            mk = _match_keyword(job.get("title",""), job.get("description",""), [kw])
            if not mk and not PPH_SEND_ALL:
                continue

            job["matched_keyword"] = mk or kw

            # If no budget_display yet, try from parsed data
            if "budget_display" not in job and job.get("budget_min") and job.get("currency"):
                job["budget_display"] = _convert_currency(job["budget_min"], job["currency"])

            all_items.append(job)

            if len(all_items) - count_before >= PPH_PER_KEYWORD_LIMIT:
                break

        if DEBUG_LOG:
            log.info(f"[PPH] kw={kw} -> +{len(all_items)-count_before} items (total so far {len(all_items)})")

    # De-dup by URL
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
