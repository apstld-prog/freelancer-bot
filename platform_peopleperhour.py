# platform_peopleperhour.py — Playwright Proxy Edition
# FULL VERSION — fetch search results + parse job pages
# NO RSS, NO TOR, NO httpx proxy. Everything goes through your PPH Docker Proxy.

import re
import time
import json
from typing import List, Dict, Optional
from playwright.sync_api import sync_playwright
import os

# -------------------------------------------------
# SETTINGS
# -------------------------------------------------

PPH_PROXY = os.getenv("PPH_PROXY_URL", "").strip()
if not PPH_PROXY:
    # failsafe για να μην σκάσει ο worker
    PPH_PROXY = "https://pph-proxy.onrender.com"

BASE = "https://www.peopleperhour.com"

# regex extractors for job page
META_PRICE = re.compile(r'"peopleperhourcom:price"\s+content="([\d.]+)"')
META_CURR  = re.compile(r'"peopleperhourcom:currency"\s+content="([^"]+)"')
META_DESC  = re.compile(r'<meta data-react-helmet="true" name="description" content="(.*?)"', re.S)

# -------------------------------------------------
# Helper: launch browser through proxy
# -------------------------------------------------
def _launch_browser():
    """Launch Chromium in Playwright through your proxy"""
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    )
    context = browser.new_context(
        proxy={"server": PPH_PROXY}
    )
    return playwright, browser, context

# -------------------------------------------------
# Fetch search result URLs
# -------------------------------------------------
def _search_urls(keyword: str) -> List[str]:
    """Retrieve up to ~20 job links from PPH search"""
    keyword = keyword.strip().replace(" ", "%20")
    url = f"{BASE}/freelance-jobs?q={keyword}"

    playwright, browser, context = _launch_browser()
    page = context.new_page()

    try:
        page.goto(url, timeout=30000)
        page.wait_for_timeout(1500)

        links = page.locator("a[href*='/freelance-jobs/']").all()
        out = []
        for a in links:
            href = a.get_attribute("href") or ""
            if "/freelance-jobs/" in href and "?" not in href:
                full = BASE + href if href.startswith("/") else href
                if full not in out:
                    out.append(full)
        return out[:20]

    except Exception:
        return []

    finally:
        context.close()
        browser.close()
        playwright.stop()

# -------------------------------------------------
# Extract details from job page
# -------------------------------------------------
def _scrape_job(url: str) -> Dict:
    playwright, browser, context = _launch_browser()
    page = context.new_page()

    try:
        page.goto(url, timeout=40000)
        html = page.content()

        # extract fields
        price = None
        curr = None

        m = META_PRICE.search(html)
        if m:
            try: price = float(m.group(1))
            except: pass

        m = META_CURR.search(html)
        if m:
            curr = m.group(1).replace("£","GBP").replace("€","EUR")

        m = META_DESC.search(html)
        desc = m.group(1).strip() if m else ""

        return {
            "title": page.title() or "",
            "budget_min": price,
            "budget_max": price,
            "currency": curr or "USD",
            "currency_display": curr or "USD",
            "description": desc,
            "description_html": desc,
            "original_url": url,
            "proposal_url": url,
            "source": "peopleperhour",
            "time_submitted": int(time.time()),
        }

    except Exception:
        return {}

    finally:
        context.close()
        browser.close()
        playwright.stop()

# -------------------------------------------------
# Public API
# -------------------------------------------------
def get_items(keywords: List[str]) -> List[Dict]:
    """Search keyword → get URLs → scrape each job page."""
    out: List[Dict] = []
    for kw in keywords:
        links = _search_urls(kw)
        for url in links:
            data = _scrape_job(url)
            if data:
                data["matched_keyword"] = kw
                out.append(data)
    return out
