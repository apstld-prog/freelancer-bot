import asyncio
from playwright.async_api import async_playwright
import re

# ---------------------------------------------------------
# Clean helper
# ---------------------------------------------------------
def _clean(s):
    return (s or "").strip()

# ---------------------------------------------------------
# Budget extractor
# ---------------------------------------------------------
def _extract_budget(text):
    """
    Converts prices like:
      $40
      £50 - £200
      €120
    into:
      min, max, currency
    """
    if not text:
        return None, None, None

    txt = text.replace(",", "").strip()

    if "£" in txt:
        cur = "GBP"
    elif "€" in txt:
        cur = "EUR"
    elif "$" in txt:
        cur = "USD"
    else:
        cur = None

    cleaned = txt.replace("£", "").replace("€", "").replace("$", "")
    numbers = re.findall(r"\d+(?:\.\d+)?", cleaned)

    if not numbers:
        return None, None, cur

    nums = list(map(float, numbers))

    if len(nums) == 1:
        return nums[0], nums[0], cur
    else:
        return nums[0], nums[-1], cur


# ---------------------------------------------------------
# MAIN SCRAPER
# ---------------------------------------------------------
async def _scrape_keyword(kw):
    """
    Scrape one keyword from:
    https://www.peopleperhour.com/freelance-jobs?q=KEYWORD
    """

    items = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu"]
        )
        page = await browser.new_page()

        url = f"https://www.peopleperhour.com/freelance-jobs?q={kw}"
        await page.goto(url, timeout=60000)

        await page.wait_for_selector("li.list__item", timeout=60000)

        cards = await page.query_selector_all("li.list__item")

        for card in cards:
            # Title
            a = await card.query_selector("a.item__url")
            if not a:
                continue

            title = _clean(await a.inner_text())
            href = await a.get_attribute("href")
            if href.startswith("/"):
                href = "https://www.peopleperhour.com" + href

            # Description
            desc_tag = await card.query_selector("p.item__desc")
            description = _clean(await desc_tag.inner_text()) if desc_tag else ""

            full_text = f"{title} {description}".lower()
            if kw.lower() not in full_text:
                continue

            # Price
            price_span = await card.query_selector("div.card__price span span")
            price = ""
            if price_span:
                price = _clean(await price_span.inner_text())

            bmin, bmax, cur = _extract_budget(price)

            item = {
                "source": "peopleperhour",
                "matched_keyword": kw,
                "title": title,
                "description": description,
                "original_url": href,
                "budget_min": bmin,
                "budget_max": bmax,
                "original_currency": cur
            }

            items.append(item)

        await browser.close()
        return items


# ---------------------------------------------------------
# Public API
# ---------------------------------------------------------
def get_items(keywords):
    """
    Synchronous wrapper so workers can call it normally.
    """

    async def runner():
        all_items = []
        for kw in keywords:
            batch = await _scrape_keyword(kw)
            all_items.extend(batch)
        return all_items

    return asyncio.run(runner())
