# platform_peopleperhour.py
# Direct PeoplePerHour scraping (no proxy, no cloudflare block)

import httpx
import re
import logging
from bs4 import BeautifulSoup

log = logging.getLogger("pph-direct")

BASE_URL = "https://www.peopleperhour.com/freelance-jobs?page={page}&filter=skills&query={query}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

TIMEOUT = httpx.Timeout(15.0, connect=10.0)


def _fetch_html(url: str) -> str:
    """Fetch raw HTML with smart headers."""
    try:
        with httpx.Client(headers=HEADERS, timeout=TIMEOUT, verify=False) as c:
            r = c.get(url, follow_redirects=True)
            if r.status_code != 200:
                log.warning(f"PPH HTML HTTP {r.status_code}")
                return ""
            return r.text
    except Exception as e:
        log.error(f"PPH fetch error: {e}")
        return ""


def _parse_jobs(html: str):
    """Parse HTML page → list of jobs."""
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")

    jobs = []
    cards = soup.select("article, div.card, div.job")  # broad selector

    for card in cards:
        text = card.get_text(" ", strip=True).lower()
        if not text:
            continue

        # ----- extract title -----
        title_tag = card.find(["h2", "h3", "a"])
        title = title_tag.get_text(strip=True) if title_tag else "Untitled"

        # ----- description guess -----
        desc = ""
        p = card.find("p")
        if p:
            desc = p.get_text(" ", strip=True)

        # ----- link -----
        link = ""
        a = card.find("a", href=True)
        if a:
            href = a["href"]
            if href.startswith("/"):
                link = "https://www.peopleperhour.com" + href
            else:
                link = href

        # ----- budget (regex search) -----
        budget_min = None
        budget_max = None
        currency = None

        m = re.search(r"£\s*([0-9]+)", card.get_text(" ", strip=True))
        if m:
            budget_min = budget_max = float(m.group(1))
            currency = "GBP"

        m2 = re.search(r"\$?\s*([0-9]+)\s*-\s*\$?([0-9]+)", card.get_text(" ", strip=True))
        if m2:
            budget_min = float(m2.group(1))
            budget_max = float(m2.group(2))
            if "$" in card.get_text():
                currency = "USD"

        # ----- build job -----
        job = {
            "title": title,
            "description": desc,
            "budget_min": budget_min,
            "budget_max": budget_max,
            "original_currency": currency or "USD",
            "url": link,
            "source": "PeoplePerHour",
            "timestamp": None,  # PPH hides timestamps on public pages
        }

        jobs.append(job)

    return jobs


def _fetch_all_keywords(keywords, pages=3):
    """Fetch + parse jobs for each keyword."""
    all_jobs = []

    for kw in keywords:
        for p in range(1, pages + 1):
            url = BASE_URL.format(page=p, query=kw)
            html = _fetch_html(url)
            parsed = _parse_jobs(html)
            for j in parsed:
                j["matched_keyword"] = kw
            all_jobs.extend(parsed)

    return all_jobs


def get_items(keywords):
    """Main function called by worker."""
    return _fetch_all_keywords(keywords, pages=3)
