import httpx
from bs4 import BeautifulSoup
import re

def _clean(s):
    return (s or "").strip()

def _extract_budget(text):
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


def get_items(keywords):
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    for kw in keywords or []:
        url = f"https://www.peopleperhour.com/freelance-jobs?q={kw}"

        try:
            r = httpx.get(url, headers=headers, timeout=20)
            soup = BeautifulSoup(r.text, "html.parser")

            # CORRECT SELECTOR
            cards = soup.select("li.list__item")

            for card in cards:

                # Title
                a = card.select_one("h6 a")
                if not a:
                    continue
                title = _clean(a.text)
                href = a["href"]
                if href.startswith("/"):
                    href = "https://www.peopleperhour.com" + href

                # Description
                desc_tag = card.select_one("p")
                description = _clean(desc_tag.text) if desc_tag else ""

                # Keyword match
                hay = f"{title} {description}".lower()
                if kw.lower() not in hay:
                    continue

                # Budget
                price_tag = card.select_one(".card__price span span")
                if not price_tag:
                    price_tag = card.select_one(".card__price span")

                price = _clean(price_tag.text) if price_tag else ""
                bmin, bmax, cur = _extract_budget(price)

                # Convert to USD like freelancer
                rate = {"EUR":1.08, "GBP":1.27, "USD":1.0}
                if cur in rate:
                    bmin_usd = round(bmin * rate[cur], 2) if bmin else None
                    bmax_usd = round(bmax * rate[cur], 2) if bmax else None
                else:
                    bmin_usd = bmin
                    bmax_usd = bmax

                item = {
                    "source": "peopleperhour",
                    "title": title,
                    "description": description,
                    "original_url": href,
                    "budget_min": bmin_usd,
                    "budget_max": bmax_usd,
                    "original_currency": cur,
                    "matched_keyword": kw,
                }
                results.append(item)

        except Exception as e:
            print("PPH ERROR:", e)

    return results
