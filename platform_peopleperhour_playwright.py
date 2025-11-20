
import asyncio
from playwright.async_api import async_playwright

BASE = "https://www.peopleperhour.com"

async def _scrape_job(page, url):
    await page.goto(url, wait_until="networkidle")
    title = await page.title()
    return {
        "title": title,
        "original_url": url,
        "proposal_url": url,
        "description_html": "",
        "time_submitted": "",
        "budget_min": None,
        "budget_max": None,
        "currency": None,
        "currency_display": "USD",
        "source": "peopleperhour",
        "matched_keyword": ""
    }

async def get_items_playwright(keywords):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page()
        results = []
        for kw in keywords:
            search_url = f"{BASE}/freelance-jobs?q={kw}"
            data = await _scrape_job(page, search_url)
            data["matched_keyword"] = kw
            results.append(data)
        await browser.close()
        return results
