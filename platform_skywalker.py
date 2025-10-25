import httpx
import logging
import asyncio
from bs4 import BeautifulSoup
from utils import convert_to_usd, format_time_ago

logger = logging.getLogger("skywalker")

BASE_URL = "https://www.skywalker.gr/elGR/aggelies"

async def fetch_skywalker_jobs(keyword):
    """Fetch and format job results from Skywalker using HTML parsing."""
    jobs = []
    try:
        search_url = f"{BASE_URL}?keyword={keyword}"
        headers = {"User-Agent": "Mozilla/5.0 (compatible; FreelancerBot/1.0)"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(search_url, headers=headers)
            if response.status_code == 429:
                logger.warning(f"[Skywalker] Rate-limited for keyword '{keyword}', sleeping 20s...")
                await asyncio.sleep(20)
                return []
            response.raise_for_status()
            html = response.text
    except Exception as e:
        logger.error(f"[Skywalker] Error fetching keyword '{keyword}': {e}")
        return jobs

    try:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.list-group-item")
        if not cards:
            logger.info(f"[Skywalker] No jobs found for keyword '{keyword}'")
            return jobs

        for card in cards:
            try:
                title_tag = card.select_one("h2 a")
                title = title_tag.text.strip() if title_tag else "Untitled"
                url = (
                    f"https://www.skywalker.gr{title_tag['href']}"
                    if title_tag and title_tag.has_attr("href")
                    else BASE_URL
                )

                desc_tag = card.select_one("p")
                desc = desc_tag.text.strip() if desc_tag else ""

                date_tag = card.select_one("div.pull-right span")
                posted_text = date_tag.text.strip() if date_tag else "N/A"

                # Skywalker does not provide budget info
                amount, currency = 0, "EUR"
                usd_value = convert_to_usd(amount, currency)

                formatted = (
                    f"<b>🧭 Platform:</b> Skywalker\n"
                    f"<b>📄 Title:</b> {title}\n"
                    f"<b>🔑 Keyword:</b> {keyword}\n"
                    f"<b>💰 Budget:</b> {currency} {amount} (~${usd_value} USD)\n"
                    f"<b>🕓 Posted:</b> {posted_text}\n\n"
                    f"{desc}\n\n"
                    f"<a href='{url}'>🔗 View Project</a>"
                )

                jobs.append({
                    "platform": "Skywalker",
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
                logger.warning(f"[Skywalker] Skipped one job due to parse error: {e}")

        logger.info(f"[Skywalker] Retrieved {len(jobs)} jobs for keyword '{keyword}'")

    except Exception as e:
        logger.error(f"[Skywalker] Parse error: {e}")

    return jobs
