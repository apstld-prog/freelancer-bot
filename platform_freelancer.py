
import requests
from typing import List, Dict

API = "https://www.freelancer.com/api/projects/0.1/projects/active/"
# The public endpoint works without auth for basic queries; tune params as needed.

DEFAULT_PARAMS = {
    "limit": 50,
    "compact": "true",
    "user_details": "true",
    "job_details": "true",
    "full_description": "true",
    # 'query': 'python, telegram'  # set by caller if needed
}

def _extract_budget(p: dict):
    b = (p or {}).get("budget") or {}
    minimum = b.get("minimum")
    maximum = b.get("maximum")
    currency = (b.get("currency") or {}).get("code") or "USD"
    return minimum, maximum, currency

def _item_from_project(p: dict) -> Dict:
    min_b, max_b, ccy = _extract_budget(p)
    title = p.get("title") or ""
    desc = p.get("preview_description") or p.get("description") or ""
    seo_url = (p.get("seo_url") or "").lstrip("/")
    url = f"https://www.freelancer.com/projects/{seo_url}" if seo_url else "https://www.freelancer.com"
    return {
        "external_id": str(p.get("id")),
        "title": title,
        "description": desc,
        "url": url,
        "budget_min": min_b,
        "budget_max": max_b,
        "currency": ccy,
        "source": "freelancer",
        "affiliate": True,
    }

def fetch(query: str = None, country_codes: List[str] = None, limit: int = 50) -> List[Dict]:
    params = dict(DEFAULT_PARAMS)
    params["limit"] = limit
    if query:
        params["query"] = query
    # country filter optional. Freelancer supports location filters via advanced params;
    # here we keep it simple for compatibility.
    try:
        r = requests.get(API, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        r.raise_for_status()
        data = r.json() or {}
        projects = (data.get("result") or {}).get("projects") or []
        return [_item_from_project(p) for p in projects]
    except Exception:
        return []
