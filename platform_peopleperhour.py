# platform_peopleperhour.py
# FULL LISTING SCRAPER (χωρίς search, χωρίς RSS)
# Παίρνει πάντα όλες τις νέες αγγελίες από το main listing.

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import re

LISTING_URL = "https://www.peopleperhour.com/freelance-jobs"

def _clean(txt):
    return (txt or "").strip()

def _parse_budget(txt):
    if not txt:
        return None, None, None
    txt = txt.replace(",", "").strip()

    # Examples: "$150", "£40", "€200", "$10-20"
    m = re.findall(r"([£$€])\s?(\d+(?:\.\d+)?)", txt)
    if not m:
        return None, None, None

    symbol = m[0][0]
    currency = {"$": "USD", "£": "GBP", "€": "EUR"}.get(symbol, "USD")

    nums = [float(a[1]) for a in m]
    if len(nums) == 1:
        return nums[0], nums[0], currency
    return nums[0], nums[1], currency


def get_items(keywords):
    """
    Διαβάζει τα τελευταία ~200 jobs από το main listing.
    Το worker θα κάνει keyword-filter + matched_keyword.
    """
    out = []
    try:
        r = requests.get(LISTING_URL, timeout=10)
        html = BeautifulSoup(r.text, "html.parser")
    except Exception:
        return out

    cards = html.select("a.job-listing-card")  # νέο layout PPH
    for c in cards[:200]:
        title = _clean(c.select_one("h3"))
        if hasattr(title, "text"):
            title = _clean(title.text)

        desc = _clean(c.select_one("p"))
        if hasattr(desc, "text"):
            desc = _clean(desc.text)

        url = c.get("href", "")
        if url.startswith("/"):
            url = "https://www.peopleperhour.com" + url

        # Budget line
        bud = c.select_one(".job-price")
        budtxt = _clean(bud.text if bud else "")

        bmin, bmax, currency = _parse_budget(budtxt)

        # Time
        ts = int(datetime.now(timezone.utc).timestamp())

        item = {
            "source": "peopleperhour",
            "matched_keyword": None,        # Worker will set this
            "title": title,
            "description": desc,
            "external_id": url,
            "url": url,
            "proposal_url": url,
            "original_url": url,
            "budget_min": bmin,
            "budget_max": bmax,
            "original_currency": currency,
            "currency": currency,
            "time_submitted": ts,
            "affiliate": False,
        }
        out.append(item)

    return out
