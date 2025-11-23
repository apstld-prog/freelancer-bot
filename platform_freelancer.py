# FINAL platform_freelancer.py
import httpx
from typing import List, Dict

API = "https://www.freelancer.com/api/projects/0.1/projects/active/"

def get_items(keywords: List[str]) -> List[Dict]:
    out=[]
    try:
        r = httpx.get(API, timeout=10)
        if r.status_code != 200:
            return out
        data = r.json()
    except:
        return out

    rows = data.get("result", {}).get("projects", [])
    for kw in keywords:
        for p in rows:
            title = p.get("title", "")
            if kw.lower() in title.lower():
                out.append({
                    "source": "freelancer",
                    "matched_keyword": kw,
                    "title": title,
                    "original_url": f"https://www.freelancer.com/projects/{p.get('seo_url', '')}",
                    "proposal_url": f"https://www.freelancer.com/projects/{p.get('seo_url', '')}",
                    "description": p.get("description", ""),
                    "description_html": p.get("description", ""),
                    "budget_min": p.get("budget", {}).get("minimum", None),
                    "budget_max": p.get("budget", {}).get("maximum", None),
                    "currency": p.get("budget", {}).get("currency", "USD"),
                    "time_submitted": p.get("submitdate", None),
                })
    return out
