# platform_peopleperhour_browser.py
# PeoplePerHour Browser Scraper via Playwright (headless Chromium)

import asyncio
from playwright.async_api import async_playwright
import logging
import re

log = logging.getLogger("pph_browser")

BASE = "https://www.peopleperhour.com/freelance-jobs?page={page}&filter=skills&query={query}"

# Clean budget extraction (handles £, $, ranges etc)
def extract_budget(text):
    # e.g. £30, $50–$120, 40 - 80 USD
    text = text.replace(",", "")
    m1 = re.search(r"([£$]?)(\d+)\s*[-–]\s*([£$]?)(\d+)", text)
    if m1:
        min_v = float(m1.group(2))
        max_v = float(m1.group(4))
        cur = m1.group(1) or m1.group(3) or "USD"
        if cur == "£": cur = "GBP"
        if cur == "$": cur = "USD"
        return min_v, max_v, cur

    m2 = re.search(r"([£$])(\d+)", text)
    if m2:
        v = float(m2.group(2))
        cur = m2.group(1)
        if cur == "£": cur = "GBP"
        if cur == "$": cur = "USD"
        return v, v, cur

    return None, None, None


async def fetch_keyword(keyword: str, pages: int = 3):
    """Fetch jobs for a single keyword across N pages."""
    jobs = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 2000}
        )
        page_obj = await ctx.new_page()

        for p in range(1, pages + 1):
            url = BASE.format(page=p, query=keyword)
            log.info(f"[PPH] Fetching: {url}")

            try:
                await page_obj.goto(url, timeout=30000, wait_until="domcontentloaded")
                await page_obj.wait_for_timeout(2000)  # allow JS to render cards
            except Exception as e:
                log.warning(f"PPH navigation error: {e}")
                continue

            cards = await page_obj.query_selector_all("article, div, section")

            for c in cards:
                try:
                    t = (await c.inner_text()).strip()
                except Exception:
                    continue

                # Skip empty blocks
                if not t or len(t) < 30:
                    continue

                # Titles on PPH tend to be in <h3>, <h2>, <a>, etc.
                try:
                    title_el = await c.query_selector("h3, h2, a")
                    title = (await title_el.inner_text()).strip() if title_el else "Untitled"
                except:
                    title = "Untitled"

                # Description guess
                desc = ""
                try:
                    ptag = await c.query_selector("p")
                    if ptag:
                        desc = (await ptag.inner_text()).strip()
                except:
                    pass

                # URL
                job_url = ""
                try:
                    a = await c.query_selector("a[href]")
                    if a:
                        href = await a.get_attribute("href")
                        if href:
                            if href.startswith("/"):
                                job_url = "https://www.peopleperhour.com" + href
                            else:
                                job_url = href
                except:
                    pass

                # Budget parsing
                min_b, max_b, cur = extract_budget(t)

                job = {
                    "title": title,
                    "description": desc,
                    "budget_min": min_b,
                    "budget_max": max_b,
                    "original_currency": cur or "USD",
                    "url": job_url,
                    "source": "PeoplePerHour",
                    "timestamp": None,  # PPH hides timestamps
                    "matched_keyword": keyword
                }

                # Heuristic: Only include cards that look like job posts
                if len(title) > 5 and job_url:
                    jobs.append(job)

        await ctx.close()
        await browser.close()

    return jobs


def get_items(keywords, pages=3):
    """Main entry: Playwright browser scraper."""
    results = []

    # Run all keywords in a single event loop
    async def run_all():
        for kw in keywords:
            items = await fetch_keyword(kw, pages)
            results.extend(items)

    asyncio.get_event_loop().run_until_complete(run_all())
    return results
