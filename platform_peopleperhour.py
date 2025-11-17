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
    Detects:
      $40
      £50 - £200
      €120
      $1.2k
    Returns:
      min, max, currency
    """
    if not text:
        return None, None, None

    t = text.lower().replace(",", "").strip()

    # Currency
    if "£" in t:
        cur = "GBP"
    elif "€" in t:
        cur = "EUR"
    elif "$" in t:
        cur = "USD"
    else:
        cur = None

    # Remove currency symbols
    cleaned = t.replace("£", "").replace("€", "").replace("$", "")

    # Convert shorthand like 1.3k → 1300
    cleaned = re.sub(r"(\d+(?:\.\d+)?)k", lambda m: str(float(m.group(1)) * 1000), cleaned)

    nums = re.findall(r"\d+(?:\.\d+)?", cleaned)

    if not nums:
        return None, None, cur

    nums = list(map(float, nums))

    if len(nums) == 1:
        return nums[0], nums[0], cur
    else:
        return nums[0], nums[-1], cur


# ---------------------------------------------------------
# MAIN SCRAPER (no Playwright)
# ---------------------------------------------------------
def get_items(keywords):
    results = []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        )
    }

    for kw in keywords:

        url = f"https://www.peopleperhour.com/freelance-jobs?q={kw}"

        try:
            r = httpx.get(url, headers=headers, timeout=25)
        except Exception:
            continue

        soup = BeautifulSoup(r.text, "html.parser")

        # Find item cards
        cards = soup.select("li.list__item")

        for card in cards:

            # Title + URL
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

            # Keyword filter
            hay = f"{title} {description}".lower()
            if kw.lower() not in hay:
                continue

            # Price
            price_tag = card.select_one("div.card__price span span")
            price = _clean(price_tag.text) if price_tag else ""

            bmin, bmax, cur = _extract_budget(price)

            # Save
            results.append({
                "source": "peopleperhour",
                "matched_keyword": kw,
                "title": title,
                "description": description,
                "original_url": href,
                "budget_min": bmin,
                "budget_max": bmax,
                "original_currency": cur
            })

    return results
