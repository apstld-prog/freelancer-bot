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
    Μετατρέπει:  $40  ή  £50 - £200  ή  €120
    σε:
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
    return nums[0], nums[-1], cur


# ---------------------------------------------------------
# MAIN SCRAPER
# ---------------------------------------------------------

def get_items(keywords):
    """
    Scrapes PeoplePerHour search results:
      https://www.peopleperhour.com/freelance-jobs?q=KEYWORD

    και γυρίζει items όπως ο freelancer scraper:
      title, description, original_url, budget_min, budget_max,
      original_currency, matched_keyword, source="peopleperhour"
    """

    results = []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        )
    }

    for kw in (keywords or []):
        if not kw:
            continue

        search_url = f"https://www.peopleperhour.com/freelance-jobs?q={kw}"

        try:
            r = httpx.get(search_url, headers=headers, timeout=25)
            soup = BeautifulSoup(r.text, "html.parser")

            # ---------------------------------------------------------
            # Οι PPH αγγελίες βρίσκονται μέσα σε sections με αυτό το class
            # ---------------------------------------------------------
            cards = soup.select("section.css-1qb12g8")

            for card in cards:

                # -------------------- ΤΙΤΛΟΣ --------------------
                a = card.select_one("a.css-10klw3m, a.css-1wr6c27")
                if not a:
                    continue

                title = _clean(a.text)
                href = a.get("href") or ""

                if href.startswith("/"):
                    href = "https://www.peopleperhour.com" + href

                # -------------------- DESCRIPTION --------------------
                desc_tag = card.select_one("p")
                description = _clean(desc_tag.text) if desc_tag else ""

                # -------------------- STRICT KEYWORD MATCH --------------------
                hay = f"{title} {description}".lower()
                if kw.lower() not in hay:
                    continue

                # -------------------- BUDGET --------------------
                price_tag = card.find("span", string=re.compile(r"[\$£€]\s*\d+"))
                price = _clean(price_tag.text) if price_tag else ""

                bmin, bmax, currency = _extract_budget(price)

                # -------------------- BUILD ITEM --------------------
                item = {
                    "source": "peopleperhour",
                    "title": title,
                    "description": description,
                    "original_url": href,
                    "budget_min": bmin,
                    "budget_max": bmax,
                    "original_currency": currency,
                    "matched_keyword": kw,
                }

                results.append(item)

        except Exception:
            continue

    return results
