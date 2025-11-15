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

    # detect currency
    if "£" in txt:
        cur = "GBP"
    elif "€" in txt:
        cur = "EUR"
    elif "$" in txt:
        cur = "USD"
    else:
        cur = None

    # remove symbols for parsing
    cleaned = txt.replace("£", "").replace("€", "").replace("$", "")
    numbers = re.findall(r"\d+(?:\.\d+)?", cleaned)

    if not numbers:
        return None, None, cur

    nums = list(map(float, numbers))

    if len(nums) == 1:
        return nums[0], nums[0], cur
    else:
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

        url = f"https://www.peopleperhour.com/freelance-jobs?q={kw}"

        try:
            r = httpx.get(url, headers=headers, timeout=25)
            soup = BeautifulSoup(r.text, "html.parser")

            # ---------------------------------------------------------
            # Βρίσκουμε όλες τις κάρτες αγγελιών
            # ---------------------------------------------------------
            cards = soup.select("div.card, div.listing, div")  # fallback

            for card in cards:

                # ------------------------- Title -------------------------
                a = card.find("a", href=True)
                if not a:
                    continue
                title = _clean(a.text)
                href = a["href"]
                if href.startswith("/"):
                    href = "https://www.peopleperhour.com" + href

                # keyword match check
                if kw.lower() not in (title.lower()):
                    # Expand: include description text later
                    pass

                # ------------------------- Description -------------------------
                desc_tag = card.find("p")
                description = _clean(desc_tag.text) if desc_tag else ""

                # strict keyword filter (όπως freelancer)
                hay = f"{title} {description}".lower()
                if kw.lower() not in hay:
                    continue

                # ------------------------- Budget -------------------------
                # Many PPH listings place price inside <span>$40</span>
                price_tag = card.find("span")
                price = _clean(price_tag.text) if price_tag else ""

                bmin, bmax, currency = _extract_budget(price)

                # ------------------------- Item -------------------------
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
