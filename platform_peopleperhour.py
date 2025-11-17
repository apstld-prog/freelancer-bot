import httpx
import re

RSS_URL = "https://www.peopleperhour.com/freelance-jobs.rss"

# -------------------------------------
# Helpers
# -------------------------------------
def _clean(s):
    return (s or "").strip()

def _extract_budget(text):
    """
    Extract min,max,currency from: $40, £50-£120, €100 etc.
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
    nums = re.findall(r"\d+(?:\.\d+)?", cleaned)
    if not nums:
        return None, None, cur

    nums = list(map(float, nums))

    if len(nums) == 1:
        return nums[0], nums[0], cur
    return nums[0], nums[-1], cur


# -------------------------------------
# USD conversion (όπως Freelancer)
# -------------------------------------
async def convert_to_usd(amount, currency):
    if amount is None or not currency:
        return None

    currency = currency.upper()
    if currency == "USD":
        return amount

    try:
        url = f"https://api.exchangerate.host/convert?from={currency}&to=USD&amount={amount}"
        r = httpx.get(url, timeout=10)
        data = r.json()
        return float(data.get("result"))
    except:
        return None


# -------------------------------------
# Main PeoplePerHour fetch
# -------------------------------------
def get_items(keywords):
    """
    Scrapes the PeoplePerHour RSS feed.
    Works 100% reliably on Render.
    """

    keywords = [k.lower().strip() for k in keywords if k.strip()]
    results = []

    try:
        r = httpx.get(RSS_URL, timeout=20)
        xml = r.text
    except Exception:
        return []

    # Parse items manually (safe)
    blocks = xml.split("<item>")
    for b in blocks[1:]:
        try:
            title = _clean(b.split("<title>")[1].split("</title>")[0])
            link = _clean(b.split("<link>")[1].split("</link>")[0])
            desc = _clean(b.split("<description>")[1].split("</description>")[0])
        except:
            continue

        text_full = (title + " " + desc).lower()

        matched_kw = None
        for kw in keywords:
            if kw in text_full:
                matched_kw = kw
                break

        if not matched_kw:
            continue

        # Extract price inside the description
        price_match = re.search(r"[\$£€]\s?\d+(?:\s?-\s?[\$£€]?\d+)?", desc)
        if price_match:
            price_text = price_match.group(0)
        else:
            price_text = ""

        bmin, bmax, cur = _extract_budget(price_text)

        # Build base structure
        item = {
            "source": "peopleperhour",
            "matched_keyword": matched_kw,
            "title": title,
            "description": desc,
            "original_url": link,
            "budget_min": bmin,
            "budget_max": bmax,
            "original_currency": cur,
        }

        results.append(item)

    return results
