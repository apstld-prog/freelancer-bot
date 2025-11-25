# platform_peopleperhour_browser.py
# FULL ASYNC PeoplePerHour browser scraper via Playwright

import re
import logging
from playwright.async_api import async_playwright

log = logging.getLogger("pph_browser")

BASE = "https://www.peopleperhour.com/freelance-jobs?page={page}&filter=skills&query={query}"


def extract_budget(text: str):
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
    """Async scraping για ένα keyword σε N σελίδες."""
    jobs = []

    try:
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 2400},
        )
        page = await ctx.new_page()

        for p in range(1, pages + 1):
            url = BASE.format(page=p, query=keyword)
            log.info(f"[PPH] Fetching: {url}")

            try:
                await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                await page.wait_for_timeout(1800)
            except Exception as e:
                log.warning(f"PPH navigation error: {e}")
                continue

            cards = await page.query_selector_all("a[href*='/job/'], article, div")

            for c in cards:
                try:
                    text = (await c.inner_text()).strip()
                except:
                    continue

                if not text or len(text) < 30:
                    continue

                # Title
                title = ""
                for sel in ["h3", "h2", "h4", "a"]:
                    try:
                        el = await c.query_selector(sel)
                        if el:
                            title = (await el.inner_text()).strip()
                            break
                    except:
                        pass

                if not title or len(title) < 3:
                    continue

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

                if not job_url:
                    continue

                # Description
                desc = ""
                try:
                    pnode = await c.query_selector("p")
                    if pnode:
                        desc = (await pnode.inner_text()).strip()
                except:
                    pass

                # Budget
                bmin, bmax, cur = extract_budget(text)

                jobs.append({
                    "title": title,
                    "description": desc,
                    "budget_min": bmin,
                    "budget_max": bmax,
                    "original_currency": cur or "USD",
                    "url": job_url,
                    "source": "PeoplePerHour",
                    "timestamp": None,
                    "matched_keyword": keyword,
                })

        await ctx.close()
        await browser.close()
        await pw.stop()

    except Exception as e:
        log.error(f"PPH global error: {e}")

    return jobs


async def get_items(keywords, pages=3):
    """async API για worker"""
    results = []
    for kw in keywords:
        results.extend(await fetch_keyword(kw, pages))
    return results
