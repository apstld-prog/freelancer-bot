import logging
import requests
from bs4 import BeautifulSoup
from utils import wrap_affiliate_link

log = logging.getLogger("platform.skywalker")

URL = "https://www.skywalker.gr/el/aggelies-ergasias?keywords="


def search_skywalker(keyword: str):
    url = URL + requests.utils.quote(keyword)
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return []
    except:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    items = soup.select("div.job-item")
    jobs = []

    for item in items:
        try:
            title_el = item.select_one("a.job-title")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            link = "https://www.skywalker.gr" + title_el.get("href", "")

            desc_el = item.select_one("div.job-description")
            desc = desc_el.get_text(strip=True) if desc_el else ""

            job_id = link.split("/")[-1].split("-")[0]

            jobs.append({
                "platform": "skywalker",
                "title": title,
                "description": desc,
                "original_url": link,
                "affiliate_url": wrap_affiliate_link(link),
                "job_id": job_id,
                "budget_amount": None,
                "budget_currency": None,
            })
        except Exception:
            continue

    return jobs
