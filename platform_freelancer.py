# platform_freelancer.py — robust Freelancer.com fetcher (v2)
# Changes vs your current file:
# - Browser-like session (headers), retries with exponential backoff (handles 429/5xx/transient)
# - Optional strict keyword matching toggle (FREELANCER_REQUIRE_KEYWORD_MATCH, default=1)
# - Safer normalization & guards; keeps same output fields expected by runner/worker
# - No UI changes

from typing import List, Dict, Optional
import os, time, json, math, datetime, random
import httpx

FREELANCER_SEARCH_URL = "https://www.freelancer.com/api/projects/0.1/projects/active/"

# ===== Env toggles =====
FREELANCER_LIMIT = int(os.getenv("FREELANCER_LIMIT", "40"))
HTTP_RETRIES = int(os.getenv("FREELANCER_HTTP_RETRIES", "3"))
HTTP_BACKOFF = float(os.getenv("FREELANCER_HTTP_BACKOFF", "1.6"))
FREELANCER_TIMEOUT = float(os.getenv("FREELANCER_TIMEOUT", "12.0"))
FREELANCER_REQUIRE_KEYWORD_MATCH = os.getenv("FREELANCER_REQUIRE_KEYWORD_MATCH", "1") == "1"

CCY_SYMBOL = {
    "USD": "$", "EUR": "€", "GBP": "£", "INR": "₹", "AUD": "A$",
    "CAD": "C$", "BRL": "R$", "JPY": "¥", "KRW": "₩", "TRY": "₺",
    "RUB": "₽", "ILS": "₪", "MXN": "MX$", "NZD": "NZ$", "ZAR": "R"
}

def _ccy_symbol(code: Optional[str]) -> str:
    c = (code or "").upper()
    return CCY_SYMBOL.get(c, c or "USD")

def _safe_num(x) -> Optional[float]:
    try:
        if x is None: return None
        f = float(x)
        if math.isnan(f): return None
        return round(f, 1)
    except Exception:
        return None

def _make_url(project) -> str:
    seo = project.get("seo_url") or ""
    if seo:
        return f"https://www.freelancer.com/projects/{seo}"
    pid = project.get("id")
    return f"https://www.freelancer.com/projects/{pid}"

def _extract_time_submitted(p) -> Optional[int]:
    ts = p.get("time_submitted") or p.get("submitdate") or p.get("submitted")
    try:
        f = float(ts)
        if f > 1e12:  # ms -> s
            f = f / 1000.0
        return int(f)
    except Exception:
        try:
            dt = datetime.datetime.fromisoformat(str(ts).replace("Z","+00:00"))
            return int(dt.timestamp())
        except Exception:
            return None

def _normalize_project(p) -> Dict:
    title = (p.get("title") or "").strip()
    desc = (p.get("preview_description") or p.get("description") or "").strip()
    url = _make_url(p)

    b = p.get("budget") or {}
    ccy = None
    if isinstance(b.get("currency"), dict):
        ccy = b["currency"].get("code")
    if not ccy and isinstance(p.get("currency"), dict):
        ccy = p["currency"].get("code")
    ccy = (ccy or "").upper() or None

    min_amt = _safe_num(b.get("minimum"))
    max_amt = _safe_num(b.get("maximum"))

    ts = _extract_time_submitted(p)
    iso = datetime.datetime.utcfromtimestamp(ts).isoformat() + "Z" if ts else None

    out = {
        "source": "freelancer",
        "title": title,
        "description": desc,
        "original_url": url,
        "budget_min": min_amt,
        "budget_max": max_amt,
        "original_currency": ccy,
        "currency_symbol": _ccy_symbol(ccy),
        "time_submitted": ts,
        "time_submitted_iso": iso,
    }
    out["currency_display"] = out["currency_symbol"] if out["currency_symbol"] else (ccy or "USD")
    out["currency"] = ccy
    return out

def _build_params(keywords_query: Optional[str]) -> Dict:
    params = {
        "full_description": False,
        "job_details": False,
        "limit": FREELANCER_LIMIT,
        "offset": 0,
        "sort_field": "time_submitted",
        "sort_direction": "desc",
    }
    if keywords_query:
        params["query"] = keywords_query
    return params

_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36",
    "Mozilla/5.0 (FreelancerFeedBot)"
]

def _client():
    headers = {
        "User-Agent": random.choice(_UAS),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Origin": "https://www.freelancer.com",
        "Referer": "https://www.freelancer.com/",
    }
    return httpx.Client(timeout=FREELANCER_TIMEOUT, headers=headers, follow_redirects=True, http2=False)

def _get_json(url: str, params: Dict) -> Optional[dict]:
    last_exc = None
    with _client() as cli:
        for attempt in range(1, HTTP_RETRIES + 1):
            try:
                r = cli.get(url, params=params)
                # Handle 429/5xx with backoff
                if r.status_code in (429, 503, 502, 504):
                    ra = r.headers.get("Retry-After")
                    wait = float(ra) if (ra and ra.isdigit()) else (HTTP_BACKOFF ** attempt)
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                return r.json()
            except Exception as e:
                last_exc = e
                time.sleep((HTTP_BACKOFF ** attempt) + random.random() * 0.5)
    return None

def _split_keywords(keywords_query: Optional[str]) -> List[str]:
    if not keywords_query:
        return []
    # Support both comma-separated and space-separated inputs
    raw = [s.strip() for s in keywords_query.replace(",", " ").split() if s.strip()]
    # de-dup while preserving order
    seen, out = set(), []
    for w in raw:
        wl = w.lower()
        if wl in seen: continue
        seen.add(wl); out.append(w)
    return out

def fetch(keywords_query: Optional[str] = None) -> List[Dict]:
    params = _build_params(keywords_query)
    data = _get_json(FREELANCER_SEARCH_URL, params)
    items: List[Dict] = []
    if not data:
        return items

    projects = (data.get("result") or {}).get("projects") or []
    kws = _split_keywords(keywords_query)
    for p in projects:
        try:
            it = _normalize_project(p)
            # keyword match
            if kws:
                hay = f"{it.get('title','').lower()}\n{it.get('description','').lower()}"
                matched = None
                for kw in kws:
                    if kw.lower() in hay:
                        matched = kw
                        break
                if matched:
                    it["matched_keyword"] = matched
                elif FREELANCER_REQUIRE_KEYWORD_MATCH:
                    # strict mode: skip non-matching
                    continue
            items.append(it)
        except Exception:
            continue
    return items
