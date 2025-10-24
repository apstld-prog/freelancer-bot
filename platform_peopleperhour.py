import httpx
from bs4 import BeautifulSoup
import logging
from datetime import datetime, timezone

log = logging.getLogger("platform_peopleperhour")

BASE_URL = "https://www.peopleperhour.com/freelance-jobs?q="


def fetch_pph_jobs(keywords):
    results = []
    for kw in keywords:
        try:
            url = f"{BASE_URL}{kw}"
            log.info(f"[PPH HTML] Fetching {url}")
            r = httpx.get(url, timeout=20)
            r.raise_for_status()

            soup = BeautifulSoup(r.text, "html.parser")
            job_cards = soup.select("section.section--card")

            if not job_cards:
                log.info(f"[PPH HTML] Found 0 listings for '{kw}'")
                continue

            for card in job_cards:
                title_tag = card.select_one("h2 a")
                title = title_tag.get_text(strip=True) if title_tag else "Untitled"
                link = title_tag["href"] if title_tag and title_tag.has_attr("href") else None
                if link and not link.startswith("http"):
                    link = "https://www.peopleperhour.com" + link

                desc_tag = card.select_one(".section-card__content")
                desc = desc_tag.get_text(strip=True) if desc_tag else ""

                budget_tag = card.select_one(".value, .budget")
                budget = budget_tag.get_text(strip=True) if budget_tag else None

                time_tag = card.select_one("time")
                if time_tag and time_tag.has_attr("datetime"):
                    try:
                        created_at = datetime.fromisoformat(time_tag["datetime"]).astimezone(timezone.utc)
                    except Exception:
                        created_at = datetime.now(timezone.utc)
                else:
                    created_at = datetime.now(timezone.utc)

                job = {
                    "title": title,
                    "description": desc,
                    "original_url": link,
                    "affiliate_url": link,
                    "source": "PeoplePerHour",
                    "budget_amount": budget,
                    "budget_currency": "GBP" if budget else None,
                    "created_at": created_at,
                }
                results.append(job)

            log.info(f"[PPH HTML] Parsed {len(results)} total listings so far")

        except Exception as e:
            log.error(f"[PPH HTML] Error fetching keyword '{kw}': {e}")

    log.info(f"[PPH total merged: {len(results)}]")
    return results
