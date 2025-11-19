# platform_peopleperhour.py — clean, stable, freelancer-like structure
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re

BASE_URL = "https://www.peopleperhour.com"
SEARCH_URL = BASE_URL + "/freelance-jobs"

def parse_budget(text):
    if not text:
        return None, None, None
    text = text.replace(",", "").strip()
    m = re.findall(r"(\d+)", text)
    if not m:
        return None, None, None
    nums = list(map(float, m))
    if "£" in text: cur = "GBP"
    elif "€" in text: cur = "EUR"
    elif "$" in text: cur = "USD"
    else: cur = None
    if len(nums)==1:
        return nums[0], nums[0], cur
    return nums[0], nums[-1], cur

def get_items(keywords):
    items = []
    try:
        for kw in keywords:
            resp = requests.get(SEARCH_URL, params={"filter": kw}, timeout=10)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("div.job-listing-card")
            for c in cards:
                title_el = c.select_one("h3")
                title = title_el.get_text(strip=True) if title_el else ""
                link = title_el.a["href"] if title_el and title_el.a else None
                if link and not link.startswith("http"):
                    link = BASE_URL + link
                desc_el = c.select_one("p.description")
                desc = desc_el.get_text(" ", strip=True) if desc_el else ""
                budget_el = c.select_one(".budget")
                btxt = budget_el.get_text(" ", strip=True) if budget_el else ""
                bmin,bmax,cur = parse_budget(btxt)
                ts = int(datetime.utcnow().timestamp())
                items.append({
                    "source": "peopleperhour",
                    "matched_keyword": kw,
                    "title": title,
                    "description": desc,
                    "external_id": link,
                    "url": link,
                    "proposal_url": link,
                    "original_url": link,
                    "budget_min": bmin,
                    "budget_max": bmax,
                    "original_currency": cur,
                    "currency": cur,
                    "time_submitted": ts,
                    "affiliate": False
                })
    except Exception:
        pass
    return items
