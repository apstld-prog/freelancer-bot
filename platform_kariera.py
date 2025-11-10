import logging
import requests
from bs4 import BeautifulSoup
from utils import wrap_affiliate_link

log = logging.getLogger("platform.kariera")

URL = "https://www.kariera.gr/ÃŽÂ¸ÃŽÂ­ÃÆ’ÃŽÂµÃŽÂ¹Ãâ€š-ÃŽÂµÃÂÃŽÂ³ÃŽÂ±ÃÆ’ÃŽÂ¯ÃŽÂ±Ãâ€š?keyword="


def search_kariera(keyword: str):
    url = URL + requests.utils.quote(keyword)
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code != 200:
            return []
    except:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    items = soup.select("div.position-card")

    jobs = []
    for item in items:
        try:
            title_el = item.select_one("a.position-card-link")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            link = "https://www.kariera.gr" + title_el.get("href", "")

            desc_el = item.select_one(".position-card-description")
            desc = desc_el.get_text(strip=True) if desc_el else ""

            job_id = link.split("/")[-1]

            jobs.append({
                "platform": "kariera",
                "title": title,
                "description": desc,
                "original_url": link,
                "affiliate_url": wrap_affiliate_link(link),
                "job_id": job_id,
                "budget_amount": None,
                "budget_currency": None,
            })
        except:
            continue

    return jobs


