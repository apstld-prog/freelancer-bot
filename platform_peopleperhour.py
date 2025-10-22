import logging
import httpx
from datetime import datetime, timezone

logger = logging.getLogger("platform_peopleperhour")

BASE_API = "https://www.peopleperhour.com/api/v1/projects"

def fetch_pph_jobs(keywords):
    """
    Fetch latest PeoplePerHour freelance jobs via official API.
    Works without proxy. Returns normalized list of job dicts.
    """
    all_jobs = []
    session = httpx.Client(timeout=25.0, headers={
        "User-Agent": "Mozilla/5.0 (compatible; PPHBot/1.0; +https://freelancer-alert-jobs-bot)"
    })

    for kw in keywords:
        try:
            url = f"{BASE_API}?search={kw}&limit=10&page=1"
            logger.info(f"[PPH] Fetching API for keyword '{kw}' → {url}")
            resp = session.get(url)

            if resp.status_code != 200:
                logger.warning(f"[PPH] Non-200 status ({resp.status_code}) for '{kw}'")
                continue

            data = resp.json()
            if not isinstance(data, dict) or "projects" not in data:
                logger.warning(f"[PPH] Unexpected JSON structure for '{kw}'")
                continue

            projects = data.get("projects", [])
            logger.info(f"[PPH] Got {len(projects)} results for '{kw}'")

            for p in projects:
                job = {
                    "platform": "peopleperhour",
                    "title": p.get("title") or "(no title)",
                    "description": (p.get("description") or "").strip()[:4000],
                    "budget_amount": p.get("budget", {}).get("amount"),
                    "budget_currency": p.get("budget", {}).get("currency"),
                    "budget_usd": convert_to_usd(
                        p.get("budget", {}).get("amount"),
                        p.get("budget", {}).get("currency")
                    ),
                    "original_url": f"https://www.peopleperhour.com/freelance-jobs/{p.get('seo_url')}",
                    "affiliate_url": f"https://www.peopleperhour.com/freelance-jobs/{p.get('seo_url')}",
                    "created_at": parse_datetime(p.get("date_created")),
                    "keyword": kw,
                }
                all_jobs.append(job)

        except Exception as e:
            logger.exception(f"[PPH] Error fetching '{kw}': {e}")

    logger.info(f"[PPH] Total merged: {len(all_jobs)}")
    return all_jobs


def parse_datetime(dt_str):
    if not dt_str:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def convert_to_usd(amount, currency):
    """Simple currency normalization for display."""
    if amount is None or not currency:
        return None
    rates = {
        "USD": 1,
        "EUR": 1.08,
        "GBP": 1.26,
        "INR": 0.012,
        "AUD": 0.66,
        "CAD": 0.73,
    }
    try:
        rate = rates.get(currency.upper(), 1)
        return round(float(amount) * rate, 2)
    except Exception:
        return None
