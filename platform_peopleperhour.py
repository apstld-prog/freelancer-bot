import feedparser
import re

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def _clean(s):
    return (s or "").strip()

def _extract_budget(text):
    """
    Converts prices like:
      $40
      £50 - £200
      €120
    into:
      min, max, currency
    """
    if not text:
        return None, None, None

    txt = text.replace(",", "").strip()

    # Currency detection
    if "£" in txt:
        cur = "GBP"
    elif "€" in txt:
        cur = "EUR"
    elif "$" in txt:
        cur = "USD"
    else:
        cur = None

    # Extract numbers
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
# Optional: convert to USD like Freelancer
# ---------------------------------------------------------
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
# MAIN FUNCTION — RSS SCRAPER
# ---------------------------------------------------------

def get_items(keywords):
    """
    Scrapes PPH RSS:
    https://www.peopleperhour.com/freelance-jobs.rss

    Returns list of:
      source="peopleperhour"
      title, description, original_url
      budget_min, budget_max, original_currency
      usd_min, usd_max
      matched_keyword
    """

    rss_url = "https://www.peopleperhour.com/freelance-jobs.rss"
    parsed = feedparser.parse(rss_url)

    results = []

    for entry in parsed.entries:
        title = _clean(entry.get("title", ""))
        description = _clean(entry.get("summary", ""))
        link = entry.get("link", "")

        full_text = f"{title} {description}".lower()

        for kw in keywords:
            if kw.lower() not in full_text:
                continue

            # Extract budget
            # PPH RSS often contains price inside title (e.g. "$30 Logo Design")
            bmin, bmax, cur = _extract_budget(title)

            # Convert to USD
            usd_min = convert_to_usd(bmin, cur) if bmin else None
            usd_max = convert_to_usd(bmax, cur) if bmax else None

            item = {
                "source": "peopleperhour",
                "matched_keyword": kw,
                "title": title,
                "description": description,
                "original_url": link,
                "budget_min": bmin,
                "budget_max": bmax,
                "original_currency": cur,
                "usd_min": usd_min,
                "usd_max": usd_max,
            }

            results.append(item)

    return results
