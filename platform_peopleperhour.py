import requests
from datetime import datetime, timezone

API_URL = "https://www.peopleperhour.com/api/projects"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.peopleperhour.com/freelance-jobs",
    "Origin": "https://www.peopleperhour.com",
    "X-Requested-With": "XMLHttpRequest",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
}

def _clean(x):
    return (x or "").strip()

def build_url(project):
    slug = project.get("seo_url_slug", "")
    pid = project.get("id")
    return f"https://www.peopleperhour.com/freelance-jobs/{slug}-{pid}"

def get_items(keywords):
    out = []
    page = 1

    while page <= 3:
        try:
            r = requests.get(
                API_URL,
                params={"page": page, "per_page": 50},
                headers=HEADERS,
                timeout=10,
            )
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
