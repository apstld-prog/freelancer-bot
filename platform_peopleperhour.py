import httpx
from bs4 import BeautifulSoup
import logging
from datetime import datetime, timezone

log = logging.getLogger("platform_peopleperhour")

BASE_URL = "https://www.peopleperhour.com/freelance-jobs?q="


def _parse_budget(text: str):
    """Normalize a budget string like '£150' → numeric + currency."""
    if not text:
        return None, None
    text = text.strip().replace(",", "")
    cur = None
    if text.startswith("£"):
        cur = "GBP"
        text = text.replace("£", "")
    elif text.startswith("$"):
        cur = "USD"
        text = text.replace("$", "")
    elif text.startswith("€"):
        cur = "EUR"
        text = text.replace("€", "")
    try:
        value = float(text.split()[0])
    except Exception:
        value = None
    return value, cur


def fetch_pph_jobs(keywords):
    results = []
    for kw in keywords:
        try:
            url = f"{BASE_URL}{kw}"
            log.info(f"[PPH HTML] Fetching {url}")
            r = httpx.get(url, timeout=25)
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

                # Parse budget text
                budget_tag = card.select_one(".value, .budget")
                budget_text = budget_tag.get_text(strip=True) if budget_tag else ""
                budget_val, currency = _parse_budget(budget_text)

                # Convert GBP/EUR → USD approx for display
                usd_amount = None
                if currency == "GBP" and budget_val:
                    usd_amount = budget_val * 1.28
                elif currency == "EUR" and budget_val:
                    usd_amount = budget_val * 1.08

                # Extract date if possible
                time_tag = card.select_one("time")
                if time_tag and time_tag.has_attr("datetime"):
                    try:
                        posted_at = datetime.fromisoformat(time_tag["datetime"]).astimezone(timezone.utc)
                    except Exception:
                        posted_at = datetime.now(timezone.utc)
                else:
                    posted_at = datetime.now(timezone.utc)

                job = {
                    "title": title,
                    "description": desc,
                    "original_url": link,
                    "affiliate_url": link,
                    "source": "PeoplePerHour",
                    "posted_at": posted_at.isoformat(),
                    "budget_amount": budget_val,
                    "budget_currency": currency or "GBP",
                    "usd_amount": usd_amount,
                    "match": kw,
                }

                # Keep only relevant results matching keyword
                if kw.lower() in (title.lower() + desc.lower()):
                    results.append(job)

            log.info(f"[PPH HTML] Parsed {len(results)} total listings so far")

        except Exception as e:
            log.error(f"[PPH HTML] Error fetching keyword '{kw}': {e}")

    log.info(f"[PPH total merged: {len(results)}]")
    return results
