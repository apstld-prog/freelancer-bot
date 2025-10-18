import logging
import requests
import time
from bs4 import BeautifulSoup

log = logging.getLogger("pph")

BASE_URL = "https://www.peopleperhour.com/freelance-jobs?search={keyword}"

def fetch_jobs(keywords):
    results = []
    for kw in keywords:
        try:
            url = BASE_URL.format(keyword=kw)
            log.info(f"PPH debug: fetching {url}")
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                log.warning(f"PPH debug: bad response {resp.status_code} for {kw}")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("section.section--card")
            log.info(f"PPH debug: found {len(cards)} cards for {kw}")

            for card in cards:
                title = card.select_one("a.title")
                title_text = title.get_text(strip=True) if title else "No title"
                link = title['href'] if title and title.has_attr('href') else ""
                desc = card.select_one("p.description")
                desc_text = desc.get_text(strip=True) if desc else ""
                budget = card.select_one(".js-budget")
                budget_text = budget.get_text(strip=True) if budget else "N/A"

                if link and not link.startswith("http"):
                    link = "https://www.peopleperhour.com" + link

                results.append({
                    "platform": "peopleperhour",
                    "title": title_text,
                    "description": desc_text,
                    "original_url": link,
                    "affiliate_url": link,
                    "budget_amount": budget_text,
                    "budget_currency": "",
                    "budget_usd": None,
                    "created_at": time.time(),
                })

        except Exception as e:
            log.exception(f"PPH debug: error fetching {kw}: {e}")
    return results


# Wrapper για συμβατότητα με worker_runner
def get_items(keywords):
    log.info("PPH debug: get_items() called")
    return fetch_jobs(keywords)
