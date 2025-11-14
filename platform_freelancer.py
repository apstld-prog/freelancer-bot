# platform_freelancer.py — robust Freelancer.com fetcher
# - Pulls recent projects (public feed)
# - Normalizes currency (code + symbol)
# - Provides budget_min/budget_max, original_currency, currency_symbol
# - Emits 'matched_keyword' when keywords_query provided
# - Leaves presentation to worker/runner
# - NEW: Expose submission time (time_submitted epoch + ISO)

from typing import List, Dict, Optional
import os, time, json, math, datetime
import httpx

# Public feed endpoint (no secret)
FREELANCER_SEARCH_URL = "https://www.freelancer.com/api/projects/0.1/projects/active/"

# Map ISO code -> symbol (display)
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
    # canonical deeplink
    seo = project.get("seo_url") or ""
    if seo:
        return f"https://www.freelancer.com/projects/{seo}"
    # fallback
    pid = project.get("id")
    return f"https://www.freelancer.com/projects/{pid}"

def _extract_time_submitted(p) -> Optional[int]:
    """
    Try hard to get a unix epoch (seconds) for time submitted.
    The API usually returns `time_submitted` as seconds since epoch.
    """
    ts = p.get("time_submitted")
    # Some payloads may use 'submitdate' or 'submitted'
    if ts is None:
        ts = p.get("submitdate") or p.get("submitted")
    # Normalize to int epoch seconds if possible
    try:
        # already epoch?
        f = float(ts)
        if f > 1e12:  # ms -> s
            f = f / 1000.0
        return int(f)
    except Exception:
        # Maybe ISO string
        try:
            dt = datetime.datetime.fromisoformat(str(ts).replace("Z","+00:00"))
            return int(dt.timestamp())
        except Exception:
            return None

def _normalize_project(p) -> Dict:
    title = p.get("title") or ""
    desc = p.get("preview_description") or p.get("description") or ""
    url = _make_url(p)

    # budget
    b = p.get("budget") or {}
    # NOTE: in some responses 'currency' sits under 'currency' or 'budget' -> 'currency'
    ccy = None
    if isinstance(b.get("currency"), dict):
        ccy = b["currency"].get("code")
    if not ccy and isinstance(p.get("currency"), dict):
        ccy = p["currency"].get("code")
    ccy = (ccy or "").upper() or None

    min_amt = _safe_num(b.get("minimum"))
    max_amt = _safe_num(b.get("maximum"))

    # time submitted
    ts = _extract_time_submitted(p)
    iso = None
    if ts:
        iso = datetime.datetime.utcfromtimestamp(ts).isoformat() + "Z"

    out = {
        "source": "freelancer",
        "title": title.strip(),
        "description": desc.strip(),
        "original_url": url,
        "budget_min": min_amt,
        "budget_max": max_amt,
        "original_currency": ccy,
        "currency_symbol": _ccy_symbol(ccy),
        # NEW:
        "time_submitted": ts,           # epoch seconds (UTC)
        "time_submitted_iso": iso,      # ISO string (UTC)
    }
    # convenience aliases used by runner
    out["currency_display"] = out["currency_symbol"] if out["currency_symbol"] else (ccy or "USD")
    out["currency"] = ccy  # keep for legacy code paths

    return out

def _build_params(keywords_query: Optional[str]) -> Dict:
    # Restrict to fixed+hourly; order by latest; basic fields
    params = {
        "full_description": False,
        "job_details": False,
        "limit": 30,               # small page for freshness
        "offset": 0,
        "sort_field": "time_submitted",
        "sort_direction": "desc",
    }
    if keywords_query:
        params["query"] = keywords_query  # comma-separated string
    return params

def fetch(keywords_query: Optional[str] = None) -> List[Dict]:
    params = _build_params(keywords_query)
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (FreelancerFeedBot)"
    }
    items: List[Dict] = []
    try:
        with httpx.Client(timeout=12.0) as cli:
            r = cli.get(FREELANCER_SEARCH_URL, params=params, headers=headers)
            r.raise_for_status()
            data = r.json()
    except Exception:
        return items

    projects = (data.get("result") or {}).get("projects") or []
    for p in projects:
        try:
            it = _normalize_project(p)
            # annotate match if we have a query list (split by comma)
            if keywords_query:
                hay = f"{it.get('title','').lower()}\n{it.get('description','').lower()}"
                for kw in [k.strip().lower() for k in keywords_query.split(",") if k.strip()]:
                    if kw and kw in hay:
                        it["matched_keyword"] = kw
                        break
            items.append(it)
        except Exception:
            continue
    return items
