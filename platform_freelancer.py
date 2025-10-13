import requests, re
from typing import List, Dict, Optional

API = "https://www.freelancer.com/api/projects/0.1/projects/active/"

DEFAULT_PARAMS = {
    "limit": 50,
    "compact": "true",
    "user_details": "true",
    "job_details": "true",
    "full_description": "true",
}

# Χαρτογράφηση συμβόλων/ονόματων σε ISO
_ALIAS = {
    "IND": "INR", "RUPEE": "INR", "₹": "INR",
    "EURO": "EUR", "€": "EUR",
    "£": "GBP", "UK": "GBP", "POUND": "GBP",
    "A$": "AUD", "AUD$": "AUD",
    "C$": "CAD", "CAD$": "CAD",
    "R$": "BRL",
}

# regex για ανίχνευση από τίτλο/περιγραφή όταν λείπει από το API
_SYM_RE = [
    (re.compile(r"₹|\bINR\b|\bRUPEE\S*\b", re.I), "INR"),
    (re.compile(r"€|\bEURO\b", re.I), "EUR"),
    (re.compile(r"£|\bGBP\b|\bPOUND\b", re.I), "GBP"),
    (re.compile(r"\bA\$\b|\bAUD\b", re.I), "AUD"),
    (re.compile(r"\bC\$\b|\bCAD\b", re.I), "CAD"),
    (re.compile(r"\bR\$\b|\bBRL\b", re.I), "BRL"),
    (re.compile(r"\bUSD\b|\bUS\$\b|\$", re.I), "USD"),
]

def _norm_cur(cur: Optional[str]) -> Optional[str]:
    if not cur:
        return None
    cur = str(cur).strip()
    if not cur:
        return None
    if cur in _ALIAS:
        return _ALIAS[cur]
    c = cur.upper()
    return _ALIAS.get(c, c)

def _infer_currency_from_text(title: str, desc: str) -> Optional[str]:
    text = f"{title or ''}\n{desc or ''}"
    for rx, code in _SYM_RE:
        if rx.search(text):
            return code
    return None

def _extract_currency_from_any(p: Dict) -> Optional[str]:
    b = p.get("budget") or {}
    cur = b.get("currency")
    if isinstance(cur, dict):
        for k in ("code", "sign", "name"):
            code = _norm_cur(cur.get(k))
            if code:
                return code
    elif isinstance(cur, str):
        code = _norm_cur(cur)
        if code:
            return code

    cur2 = p.get("currency")
    if isinstance(cur2, dict):
        for k in ("code", "sign", "name"):
            code = _norm_cur(cur2.get(k))
            if code:
                return code
    elif isinstance(cur2, str):
        code = _norm_cur(cur2)
        if code:
            return code

    code = _infer_currency_from_text(
        p.get("title", ""),
        p.get("description", "") or p.get("preview_description", "")
    )
    return code

def _extract_budget(p: Dict) -> Dict:
    b = p.get("budget") or {}
    code = _extract_currency_from_any(p)
    minb = b.get("minimum")
    maxb = b.get("maximum")
    try:
        if isinstance(minb, str): minb = float(minb)
    except Exception:
        minb = None
    try:
        if isinstance(maxb, str): maxb = float(maxb)
    except Exception:
        maxb = None
    return {"currency": code, "budget_min": minb, "budget_max": maxb}

def _project_url(p: Dict) -> str:
    """
    Φτιάχνει πάντα absolute URL: https://www.freelancer.com/projects/<cat>/<slug>
    Αποφεύγουμε SEO paths που λείπει το /projects/ (αλλιώς 404).
    """
    raw = (p.get("seo_url") or p.get("url") or "").strip()
    if raw:
        if not raw.startswith("http"):
            raw = "/" + raw.lstrip("/")
            if not raw.startswith("/projects/"):
                raw = "/projects" + raw
            raw = "https://www.freelancer.com" + raw
        return raw
    pid = p.get("id") or p.get("project_id")
    if pid:
        return f"https://www.freelancer.com/projects/{pid}"
    return ""

def _item_from_project(p: Dict) -> Dict:
    b = _extract_budget(p)
    return {
        "id": p.get("id") or p.get("project_id"),
        "title": p.get("title") or "",
        "description": p.get("preview_description") or p.get("description") or "",
        "source": "freelancer",
        "original_url": _project_url(p),
        "proposal_url": _project_url(p),
        "affiliate_url": "",
        "currency": b["currency"],
        "budget_min": b["budget_min"],
        "budget_max": b["budget_max"],
        "posted_at": p.get("time_submitted") or p.get("submitdate") or p.get("time_submitted_unix") or None,
    }

def fetch(query: Optional[str] = None, limit: int = 50) -> List[Dict]:
    params = dict(DEFAULT_PARAMS)
    params["limit"] = int(limit)
    if query:
        params["query"] = query
    try:
        r = requests.get(API, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        r.raise_for_status()
        data = r.json() or {}
        projects = (data.get("result") or {}).get("projects") or []
        return [_item_from_project(p) for p in projects]
    except Exception:
        return []
