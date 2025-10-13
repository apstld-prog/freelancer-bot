
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

_ALIAS = {"IND":"INR","RUPEE":"INR","₹":"INR","EURO":"EUR","£":"GBP","UK":"GBP","A$":"AUD","C$":"CAD","R$":"BRL"}

def _norm_cur(cur: Optional[str]) -> Optional[str]:
    if not cur: return None
    cur = str(cur).strip().upper()
    return _ALIAS.get(cur, cur)

def _extract_budget(p: Dict) -> Dict:
    b = p.get("budget") or {}
    code = None
    if isinstance(b.get("currency"), dict):
        code = b["currency"].get("code")
    code = _norm_cur(code)
    minb = b.get("minimum")
    maxb = b.get("maximum")
    return {"currency": code, "budget_min": minb, "budget_max": maxb}

def _project_url(p: Dict) -> str:
    url = (p.get("seo_url") or p.get("url") or "").strip()
    if url:
        return "https://www.freelancer.com" + url if url.startswith("/") else url
    pid = p.get("id") or p.get("project_id")
    if pid:
        return f"https://www.freelancer.com/projects/{pid}"
    return ""

def _item_from_project(p: Dict) -> Dict:
    b = _extract_budget(p)
    item = {
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
        "posted_at": p.get("time_submitted") or p.get("submitdate") or None,
    }
    return item

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
