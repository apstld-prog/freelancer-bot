import httpx
import re
import xml.etree.ElementTree as ET

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def _clean(s):
    return (s or "").strip()

def _extract_budget(text):
    """
    Extracts prices like:
      $40
      €120
      £50 - £200
    Returns:
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


# ---------------------------------------------------------
# MAIN SCRAPER – RSS feed
# ---------------------------------------------------------

def _scrape_keyword(kw):
    items = []

    url = f"https://www.peopleperhour.com/freelance-jobs.rss?q={kw}"

    try:
        r = httpx.get(url, timeout=20)
    except Exception:
        return items

    if r.status_code != 200:
        return items

    # Parse RSS
    try:
        root = ET.fromstring(r.text)
    except Exception:
        return items

    for item in root.findall(".//item"):
        title = _clean(item.findtext("title"))
        link = _clean(item.findtext("link"))
        description = _clean(item.findtext("description"))

        # keyword filter like freelancer
        hay = f"{title} {description}".lower()
        if kw.lower() not in hay:
            continue

        # extract budget from the description if present
        bmin, bmax, cur = _extract_budget(description)

        items.append({
            "source": "peopleperhour",
            "matched_keyword": kw,
            "title": title,
            "description": description,
            "original_url": link,
            "budget_min": bmin,
            "budget_max": bmax,
            "original_currency": cur,
        })

    return items


# ---------------------------------------------------------
# Public API
# ---------------------------------------------------------

def get_items(keywords):
    all_items = []
    for kw in (keywords or []):
        batch = _scrape_keyword(kw)
        all_items.extend(batch)
    return all_items
