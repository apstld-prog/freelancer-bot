# scraper_server.py
# Standalone FastAPI service that runs Playwright Chromium (UK region)

import asyncio
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from playwright.async_api import async_playwright
import re

app = FastAPI(title="PPH Browser Scraper", version="1.0")

BASE = "https://www.peopleperhour.com/freelance-jobs?page={page}&filter=skills&query={query}"

# ---------- Utility: Budget parser ----------
def extract_budget(text: str):
    text = text.replace(",", "")
    m1 = re.search(r"([£$]?)(\d+)\s*[-–]\s*([£$]?)(\d+)", text)
    if m1:
        min_v = float(m1.group(2))
        max_v = float(m1.group(4))
        cur = m1.group(1) or m1.group(3) or "$"
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


# ---------- GLOBAL BROWSER ----------
browser = None
context = None
page = None

@app.on_event("startup")
async def startup_event():
    """
    Launch persistent browser ONCE on service startup.
    """
    global browser, context, page

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)

    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36 (UK-Profile)"
        ),
        viewport={"width": 1280, "height": 2200},
        locale="en-GB"
    )

    page = await context.new_page()
    print(">>> Browser READY (UK mode enabled)")


# ---------- SINGLE KEYWORD SCRAPE ----------
async def scrape_keyword(keyword: str, pages: int = 3):
    jobs = []
    global page

    for p in range(1, pages + 1):
        url = BASE.format(page=p, query=keyword)
        try:
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(1800)
        except Exception as e:
            print("Navigation error:", e)
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

            if len(title) < 4:
                continue

            # URL
            job_url = ""
            try:
                a = await c.query_selector("a[href]")
                if a:
                    href = await a.get_attribute("href")
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

    return jobs


# ---------- HTTP API ----------
@app.get("/jobs")
async def get_jobs(keyword: str, pages: int = 3):
    items = await scrape_keyword(keyword, pages)
    return JSONResponse(items)


@app.get("/batch")
async def get_batch(kw: str, pages: int = 3):
    """
    kw='logo,design,wordpress'
    """
    keywords = [k.strip() for k in kw.split(",") if k.strip()]
    final = []

    for k in keywords:
        items = await scrape_keyword(k, pages)
        final.extend(items)

    return JSONResponse(final)


if __name__ == "__main__":
    uvicorn.run("scraper_server:app", host="0.0.0.0", port=10000, workers=1)
