import logging
import requests
from utils import wrap_affiliate_link

log = logging.getLogger("platform.freelancer")

BASE_URL = (
    "https://www.freelancer.com/api/projects/0.1/projects/active/"
    "?full_description=false&job_details=false&limit=30&offset=0"
    "&sort_field=time_submitted&sort_direction=desc&query="
)


def search_freelancer(keyword: str):
    """
    Freelancer.com API search by keyword.
    """
    url = BASE_URL + requests.utils.quote(keyword)
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code != 200:
            log.warning(f"Freelancer status: {r.status_code}")
            return []
    except Exception as e:
        log.error(f"Freelancer request error: {e}")
        return []

    data = r.json()
    if "result" not in data or "projects" not in data["result"]:
        return []

    jobs = []
    for p in data["result"]["projects"]:
        try:
            title = p.get("title", "").strip()
            desc = p.get("preview_description", "").strip()
            link = f"https://www.freelancer.com/projects/{p.get('seo_url','')}"

            job_id = str(p.get("id"))

            budget = p.get("budget")
            if budget:
                minb = budget.get("minimum")
                maxb = budget.get("maximum")
                curr = budget.get("currency", {}).get("code", None)
            else:
                minb = maxb = curr = None

            jobs.append({
                "platform": "freelancer",
                "title": title,
                "description": desc,
                "original_url": link,
                "affiliate_url": wrap_affiliate_link(link),
                "job_id": job_id,
                "budget_amount": minb,
                "budget_currency": curr,
            })
        except Exception:
            continue

    return jobs


