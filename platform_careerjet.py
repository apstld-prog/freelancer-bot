import logging
import requests
from bs4 import BeautifulSoup
from utils import wrap_affiliate_link

log = logging.getLogger("platform.careerjet")

RSS_URL = "https://www.careerjet.gr/search/rss?l=Greece&q="


def search_careerjet(keyword: str):
    url = RSS_URL + requests.utils.quote(keyword)

    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return []
    except:
        return []

    soup = BeautifulSoup(r.text, "xml")
    items = soup.find_all("item")
    jobs = []

    for item in items:
        try:
            title = item.title.text.strip()
            desc = item.description.text.strip() if item.description else ""
            link = item.link.text.strip()

            jobs.append({
                "platform": "careerjet",
                "title": title,
                "description": desc,
                "original_url": link,
                "affiliate_url": wrap_affiliate_link(link),
                "job_id": link.split("/")[-1],
                "budget_amount": None,
                "budget_currency": None,
            })
        except Exception:
            continue

    return jobs


