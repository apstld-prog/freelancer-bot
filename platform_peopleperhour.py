import httpx
import logging
import asyncio
from bs4 import BeautifulSoup
from utils import convert_to_usd, format_time_ago

logger = logging.getLogger("peopleperhour")

BASE_URL = "https://www.peopleperhour.com/freelance-jobs"

async def fetch_pph_jobs(keyword):
    """Fetch and format job results from PeoplePerHour using HTML parsing."""
    jobs = []
    try:
        search_url = f"{BASE_URL}?q={keyword}"
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; FreelancerBot/1.0)"
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(search_url, headers=headers)
            if response.status_code == 429:
                logger.warning(f"[PPH] Rate-limited for keyword '{keyword}', sleeping 20s...")
                await asyncio.sleep(20)
                return []
            response.raise_for_status()
            html = response.text
    except Exception as e:
        logger.error(f"[PPH] Error fetching keyword '{keyword}': {e}")
        return jobs

    try:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("section.job-card")
        if not cards:
            logger.info(f"[PPH] No jobs found for keyword '{keyword}'")
            return jobs

        for card in cards:
            try:
                title_tag = card.select_one("h2 a")
                title = title_tag.text.strip() if title_tag else "Untitled"
                url = title_tag["href"] if title_tag and title_tag.has_attr("href") else BASE_URL

                desc_tag = card.select_one(".job-card__description")
                desc = desc_tag.text.strip() if desc_tag else ""

                budget_tag = card.select_one(".job-card__price")
                budget_text = budget_tag.text.strip() if budget_tag else "N/A"

                # --- Parse budget properly ---
                amount, currency = 0, "USD"
                if budget_text != "N/A":
                    parts = budget_text.replace(",", "").split()
                    for part in parts:
                        if part.replace(".", "", 1).isdigit():
                            amount = float(part)
                        elif len(part) <= 4:
                            currency = part.upper()
                usd_value = convert_to_usd(amount, currency)

                # --- Posted info ---
                posted_tag = card.select_one(".job-card__date")
                posted_text = posted_tag.text.strip() if posted_tag else "N/A"

                formatted = (
                    f"<b>🧭 Platform:</b> PeoplePerHour\n"
                    f"<b>📄 Title:</b> {title}\n"
                    f"<b>🔑 Keyword:</b> {keyword}\n"
                    f"<b>💰 Budget:</b> {currency} {amount} (~${usd_value} USD)\n"
                    f"<b>🕓 Posted:</b> {posted_text}\n\n"
                    f"{desc}\n\n"
                    f"<a href='{url}'>🔗 View Project</a>"
                )

                jobs.append({
                    "platform": "PeoplePerHour",
                    "title": title,
                    "description": desc,
                    "keyword": keyword,
                    "budget_amount": amount,
                    "budget_currency": currency,
                    "budget_usd": usd_value,
                    "created_at": posted_text,
                    "url": url,
                    "formatted": formatted,
                })
            except Exception as e:
                logger.warning(f"[PPH] Skipped one job due to parse error: {e}")

        logger.info(f"[PPH] Retrieved {len(jobs)} jobs for keyword '{keyword}'")

    except Exception as e:
        logger.error(f"[PPH] Parse error: {e}")

    return jobs
