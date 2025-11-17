import httpx
from bs4 import BeautifulSoup
import re

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def _clean(s):
    return (s or "").strip()

def _extract_budget(text):
    """
    Converts values like:
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


def convert_to_usd(amount, currency):
    if not amount or not currency:
        return None
    currency = currency.upper()
    rates = {
        "USD": 1,
        "EUR": 1.08,
        "GBP": 1.27,
    }
    rate = rates.get(currency)
    if not rate:
        return None
    return round(amount * rate, 2)


# ---------------------------------------------------------
# MAIN SCRAPER — HTML PARSER
# ---------------------------------------------------------

def get_items(keywords):

    results = []

    url = "https://www.peopleperhour.com/freelance-jobs?q=" + ",".join(keywords)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        )
    }

    r = httpx.get(url, headers=headers, timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")

    cards = soup.select("li.list__item")

    for card in cards:

        # Title
        a = card.select_one("a.item__url")
        if not a:
            continue

        title = _clean(a.text)
        href = a.get("href", "")
        if href.startswith("/"):
            href = "https://www.peopleperhour.com" + href

        # Description
        desc_tag = card.select_one("p.item__desc")
        description = _clean(desc_tag.text) if desc_tag else ""

        hay = f"{title} {description}".lower()

        matched_kw = None
        for kw in keywords:
            if kw.lower() in hay:
                matched_kw = kw
                break

        if not matched_kw:
            continue

        # Budget
        price_div = card.select_one("div.card__price span span")
        price_text = _clean(price_div.text) if price_div else ""

        bmin, bmax, cur = _extract_budget(price_text)

        usd_min = convert_to_usd(bmin, cur) if bmin else None
        usd_max = convert_to_usd(bmax, cur) if bmax else None

        item = {
            "source": "peopleperhour",
            "matched_keyword": matched_kw,
            "title": title,
            "description": description,
            "original_url": href,
            "budget_min": bmin,
            "budget_max": bmax,
            "original_currency": cur,
            "usd_min": usd_min,
            "usd_max": usd_max,
        }

        results.append(item)

    return results
