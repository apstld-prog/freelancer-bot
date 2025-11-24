
# platform_freelancer.py — NEW FULL SCRAPER (2025 API)
import httpx

API = "https://www.freelancer.com/api/projects/0.1/projects/active/"

def normalize_currency(c):
    if isinstance(c, dict):
        return c.get("code","USD")
    return c or "USD"

def make_affiliate(url):
    return f"https://www.freelancer.com/get/apstld?f=give&url={url}"

def fetch(keyword):
    params = {"query": keyword, "limit": 50}
    r = httpx.get(API, params=params, timeout=20)
    if r.status_code != 200:
        return []
    data = r.json()
    projects = data.get("result", {}).get("projects", []) or []
    items=[]
    for p in projects:
        title = p.get("title","")
        desc = p.get("preview_description","") or ""
        budget = p.get("budget") or {}
        curr = normalize_currency(budget.get("currency"))
        minb = budget.get("minimum")
        maxb = budget.get("maximum")

        pid = p.get("id")
        link = p.get("seo_url") or ""
        if pid and link:
            url = f"https://www.freelancer.com/projects/{pid}/{link}"
        elif pid:
            url = f"https://www.freelancer.com/projects/{pid}"
        else:
            url = "https://www.freelancer.com"

        items.append({
            "title": title,
            "description": desc,
            "matched_keyword": keyword,
            "budget_min": minb,
            "budget_max": maxb,
            "original_currency": curr,
            "link": make_affiliate(url),
            "source": "Freelancer"
        })
    return items

def get_items(keywords):
    out=[]
    for kw in keywords:
        out.extend(fetch(kw))
    return out
