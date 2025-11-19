import requests
from datetime import datetime, timezone

API_URL = "https://www.peopleperhour.com/api/projects"

def _clean(x):
    return (x or "").strip()

def build_url(project):
    slug = project.get("seo_url_slug", "")
    pid = project.get("id")
    return f"https://www.peopleperhour.com/freelance-jobs/{slug}-{pid}"

def get_items(keywords):
    """
    Scraper που χρησιμοποιεί το κανονικό API του PPH.
    Δεν χρειάζεται keywords εδώ — το worker θα φιλτράρει.
    """
    out = []
    page = 1

    while page <= 3:  # 150 jobs max
        try:
            r = requests.get(API_URL, params={"page": page, "per_page": 50}, timeout=10)
            data = r.json()
        except Exception:
            break

        projects = data.get("projects", [])
        if not projects:
            break

        for p in projects:
            title = _clean(p.get("title"))
            desc = _clean(p.get("description"))
            url = build_url(p)

            budget = p.get("budget", {})
            bmin = budget.get("min")
            bmax = budget.get("max")
            currency = (budget.get("currency") or "USD").upper()

            ts = p.get("created_at_unix")
            if not ts:
                ts = int(datetime.now(timezone.utc).timestamp())

            item = {
                "source": "peopleperhour",
                "matched_keyword": None,
                "title": title,
                "description": desc,
                "external_id": p.get("id"),
                "url": url,
                "proposal_url": url,
                "original_url": url,
                "budget_min": bmin,
                "budget_max": bmax,
                "original_currency": currency,
                "currency": currency,
                "time_submitted": ts,
                "affiliate": False,
            }

            out.append(item)

        page += 1

    return out
