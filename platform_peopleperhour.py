import logging
import requests
from bs4 import BeautifulSoup

from utils import wrap_affiliate_link

log = logging.getLogger("platform.pph")

BASE_URL = "https://www.peopleperhour.com/freelance-jobs?page=1&searchTerm="


def search_pph(keyword: str):
    """
    Scrapes PeoplePerHour job listings based on keyword.
    """
    url = BASE_URL + requests.utils.quote(keyword)
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code != 200:
            log.warning(f"PPH returned {r.status_code}")
            return []
    except Exception as e:
        log.error(f"PPH request error: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    items = soup.select("div.project")
    jobs = []

    for item in items:
        try:
            title_el = item.select_one("h3")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)

            link_el = item.select_one("a")
            if not link_el:
                continue

            link = link_el.get("href", "")
            if not link.startswith("http"):
                link = "https://www.peopleperhour.com" + link

            desc_el = item.select_one("p.description")
            desc = desc_el.get_text(strip=True) if desc_el else ""

            budget_el = item.select_one(".project-price")
            budget = budget_el.get_text(strip=True) if budget_el else None

            jobs.append({
                "platform": "peopleperhour",
                "title": title,
                "description": desc,
                "original_url": link,
                "affiliate_url": wrap_affiliate_link(link),
                "job_id": link.split("/")[-1],
                "budget_amount": budget,
                "budget_currency": None,
            })
        except Exception:
            continue

    return jobs

