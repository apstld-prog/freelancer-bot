# platform_peopleperhour.py — PPH real jobs + budget/desc + JSON/JS ID fallback
from typing import List, Dict, Optional, Tuple
import os, re, html, urllib.parse, logging, json
from datetime import datetime, timezone, timedelta
import httpx

log = logging.getLogger("pph")

FRESH_HOURS = int(os.getenv("FRESH_WINDOW_HOURS", "48"))
USER_AGENT = os.getenv("HTTP_USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 JobBot/1.5")
PPH_SEND_ALL = os.getenv("PPH_SEND_ALL", "0") == "1"
PPH_DYNAMIC_FROM_KEYWORDS = os.getenv("PPH_DYNAMIC_FROM_KEYWORDS", "0") == "1"
PPH_BASE = os.getenv("PPH_BASE_URL", "https://www.peopleperhour.com/freelance-jobs?search={kw}")
PPH_PER_KEYWORD_LIMIT = int(os.getenv("PPH_PER_KEYWORD_LIMIT", "8"))
PPH_FALLBACK_BROWSE = os.getenv("PPH_FALLBACK_BROWSE", "1") == "1"

_CURRENCY_MAP = {"£":"GBP","€":"EUR","$":"USD","C$":"CAD","A$":"AUD","₹":"INR","NZ$":"NZD","CHF":"CHF"}
_SYM_ORDER = sorted(_CURRENCY_MAP.keys(), key=len, reverse=True)

def _parse_rss_datetime(s: str) -> Optional[datetime]:
    if not s: return None
    s = s.strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %z","%a, %d %b %Y %H:%M:%S %Z",
                "%Y-%m-%dT%H:%M:%S%z","%Y-%m-%d %H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S","%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s.replace("GMT","+0000"), fmt)
            return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
        except Exception:
            pass
    return None

def _strip_html(s: str) -> str:
    try:
        text = re.sub(r"<[^>]+>", " ", s or "", flags=re.S|re.I)
        return html.unescape(re.sub(r"\s+", " ", text)).strip()
    except Exception:
        return (s or "").strip()

def _match_keyword(title: str, description: str, keywords: List[str]) -> Optional[str]:
    hay = f"{(title or '').lower()}\n{(description or '').lower()}"
    for kw in keywords or []:
        k = (kw or "").strip().lower()
        if k and k in hay: return kw
    return None

def _terms_from_url(url: str) -> List[str]:
    try:
        q = urllib.parse.urlparse(url).query
        params = urllib.parse.parse_qs(q)
        raw = ",".join(params.get("search", [])).strip()
        if not raw: return []
        parts = re.split(r"[,+\s]+", urllib.parse.unquote_plus(raw))
        return [p.strip() for p in parts if p.strip()]
    except Exception:
        return []

def _build_urls(keywords: List[str]) -> List[str]:
    urls_env = (os.getenv("PPH_RSS_URLS","") or "").strip()
    if "{keywords}" in urls_env:
        joined = ",".join([urllib.parse.quote_plus(k.strip()) for k in keywords if k.strip()])
        return [urls_env.replace("{keywords}", joined)] if joined else []
    if PPH_DYNAMIC_FROM_KEYWORDS or not urls_env:
        urls = []
        for kw in keywords or []:
            k = kw.strip()
            if not k: continue
            urls.append(PPH_BASE.replace("{kw}", urllib.parse.quote_plus(k)))
        return urls
    return [u.strip() for u in urls_env.split(",") if u.strip()]

def _fetch(url: str, timeout: float = 15.0):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.peopleperhour.com/",
        "Accept-Language": "en-US,en;q=0.9",
    }
    r = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    return r.text, (r.headers.get("Content-Type","").lower())

# ---------- Listing → job URLs ----------
_RE_HREF_JOB = re.compile(r'href="(?P<href>/(?:job/\d+(?:-[^" ]*)?|freelance-jobs/[^/" ]+-\d+))"', re.I)
_RE_DATA_JOB = re.compile(r'data-(?:job|project)-id="(?P<id>\d+)"', re.I)
# NEW: IDs μέσα σε JSON/JS (window.__data, React props κτλ.)
_RE_JSON_JOBID = re.compile(r'(?:jobId|job_id|projectId)\s*[:=]\s*["\']?(\d{4,12})["\']?', re.I)
# NEW: πλήρη URLs μέσα σε strings
_RE_URL_IN_JS = re.compile(r'https://www\.peopleperhour\.com/(?:job/\d+(?:-[^"\'\s]*)?|freelance-jobs/[^/"\'\s]+-\d+)', re.I)
# agressive: οποιοδήποτε path που μοιάζει με job
_RE_ANY_JOB = re.compile(r'/(?:job/(\d{4,12})(?:-[^"\'\s]*)?|freelance-jobs/[^/"\'\s]+-(\d{4,12}))', re.I)

def _parse_listing_for_job_urls(html_text: str) -> List[str]:
    txt = re.sub(r"\s+", " ", html_text)
    urls, seen = [], set()

    # 1) href-based
    for m in _RE_HREF_JOB.finditer(txt):
        href = m.group("href")
        if href in seen: continue
        seen.add(href)
        urls.append("https://www.peopleperhour.com" + href)
        if len(urls) >= 60: break

    # 2) data-id cards
    if len(urls) < 12:
        for m in _RE_DATA_JOB.finditer(txt):
            jid = m.group("id")
            url = f"https://www.peopleperhour.com/job/{jid}"
            if url in urls: continue
            urls.append(url)
            if len(urls) >= 60: break

    # 3) full URLs μέσα σε JS/JSON
    if len(urls) < 12:
        for m in _RE_URL_IN_JS.finditer(txt):
            u = m.group(0)
            if u in urls: continue
            urls.append(u)
            if len(urls) >= 60: break

    # 4) σκέτα IDs μέσα σε JS/JSON
    if len(urls) < 12:
        seen_ids = set()
        for m in _RE_JSON_JOBID.finditer(txt):
            jid = m.group(1)
            if jid in seen_ids: continue
            seen_ids.add(jid)
            u = f"https://www.peopleperhour.com/job/{jid}"
            if u in urls: continue
            urls.append(u)
            if len(urls) >= 60: break

    # 5) last-resort scan paths
    if len(urls) < 8:
        for m in _RE_ANY_JOB.finditer(txt):
            path = m.group(0)
            u = "https://www.peopleperhour.com" + path if path.startswith("/") else path
            if u in urls: continue
            urls.append(u)
            if len(urls) >= 60: break

    return urls

# ---------- Job page parsing ----------
def _extract_budget(text: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    t = text
    for sym in _SYM_ORDER:
        sym_esc = re.escape(sym)
        m = re.search(rf"{sym_esc}\s*(\d+(?:[\.,]\d+)?)\s*[-–]\s*{sym_esc}?\s*(\d+(?:[\.,]\d+)?)", t)
        if m:
            a = float(m.group(1).replace(",",".")); b = float(m.group(2).replace(",","."))
            return (min(a,b), max(a,b), _CURRENCY_MAP.get(sym, sym))
        m2 = re.search(rf"{sym_esc}\s*(\d+(?:[\.,]\d+)?)\b", t)
        if m2:
            v = float(m2.group(1).replace(",","."))
            return (v, v, _CURRENCY_MAP.get(sym, sym))
    m3 = re.search(r"\b(GBP|EUR|USD|CAD|AUD|INR|NZD|CHF)\s*(\d+(?:[\.,]\d+)?)", t, re.I)
    if m3:
        code = m3.group(1).upper(); v = float(m3.group(2).replace(",","."))
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
        body, _ = _fetch(url, timeout=15)
    except Exception as e:
        log.debug("job fetch failed %s: %s", url, e); 
        return {}

    # Title
    title = None
    m = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.I|re.S)
    if m: title = _strip_html(m.group(1))
    if not title:
        m2 = re.search(r"<title[^>]*>(.*?)</title>", body, re.I|re.S)
        title = _strip_html(m2.group(1)) if m2 else ""

    # Description
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
        m4 = re.search(r"Description</[^>]+>(.{60,600})<", body, re.I|re.S)
        if m4: desc = _strip_html(m4.group(1))
    desc = (desc or "").strip()
    if len(desc) > 900: desc = desc[:900] + "…"

    # Budget
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

    # Date
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

def get_items(keywords: List[str]) -> List[Dict]:
    if not (os.getenv("ENABLE_PPH","0")=="1" and os.getenv("P_PEOPLEPERHOUR","0")=="1"):
        return []
    urls = _build_urls(keywords or [])
    if not urls: return []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=FRESH_HOURS)
    out: List[Dict] = []

    def _collect_from_listing(listing_html: str, url_terms: List[str]):
        job_urls = _parse_listing_for_job_urls(listing_html)
        for jurl in job_urls[:PPH_PER_KEYWORD_LIMIT]:
            item = _fetch_job_details(jurl)
            if not item: 
                continue
            dt = _parse_rss_datetime(item.get("date","")) or datetime.now(timezone.utc)
            if dt < cutoff:
                continue
            mk = _match_keyword(item.get("title",""), item.get("description",""), keywords or [])
            if not mk and url_terms and keywords:
                low_kws = { (k or '').strip().lower(): k for k in keywords }
                for t in url_terms:
                    lk = t.lower()
                    if lk in low_kws: mk = low_kws[lk]; break
            if mk:
                item["matched_keyword"] = mk
                out.append(item)
            else:
                if PPH_SEND_ALL:
                    if url_terms: item["matched_keyword"] = url_terms[0]
                    out.append(item)

    for url in urls:
        try:
            body, _ = _fetch(url)
        except Exception as e:
            logging.warning("PPH fetch failed: %s", e); 
            continue

        before = len(out)
        _collect_from_listing(body, _terms_from_url(url))

        if PPH_FALLBACK_BROWSE and len(out) == before:
            try:
                generic_body, _ = _fetch("https://www.peopleperhour.com/freelance-jobs")
                _collect_from_listing(generic_body, [])
            except Exception as e:
                log.debug("PPH generic fetch failed: %s", e)

    # de-dup
    seen=set(); uniq=[]
    for it in out:
        key = (it.get("url") or it.get("original_url") or "").strip() or f"pph::{(it.get('title') or '')[:160]}"
        if key in seen: continue
        seen.add(key); uniq.append(it)
    return uniq
