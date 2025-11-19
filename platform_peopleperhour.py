
# NEW PeoplePerHour Smart Scraper (Categories + Search + 24h filter)

import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re

HEADERS = {"User-Agent": "Mozilla/5.0"}

CATEGORY_MAP = {
    "logo": "https://www.peopleperhour.com/freelance-logo-jobs",
    "design": "https://www.peopleperhour.com/freelance-design-jobs",
    "branding": "https://www.peopleperhour.com/marketing-branding-jobs",
    "marketing": "https://www.peopleperhour.com/marketing-branding-jobs",
    "seo": "https://www.peopleperhour.com/digital-marketing-jobs",
    "developer": "https://www.peopleperhour.com/technology-programming-jobs",
    "website": "https://www.peopleperhour.com/technology-programming-jobs",
    "web": "https://www.peopleperhour.com/technology-programming-jobs",
    "ecommerce": "https://www.peopleperhour.com/technology-programming-jobs",
    "writing": "https://www.peopleperhour.com/writing-translation-jobs",
}

def parse_relative_time(text: str):
    if not text:
        return None
    t = text.lower()
    now = datetime.utcnow()
    nums = re.findall(r"\d+", t)
    if "hour" in t and nums:
        return now - timedelta(hours=int(nums[0]))
    if "minute" in t and nums:
        return now - timedelta(minutes=int(nums[0]))
    if "day" in t and nums:
        return now - timedelta(days=int(nums[0]))
    if "just now" in t or t.strip()=="now":
        return now
    return None

def fetch_from_page(url: str, keyword: str):
    try:
        r = httpx.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return []
    except:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    items=[]
    now = datetime.utcnow()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/freelance-jobs/" not in href:
            continue
        title = a.get_text(strip=True)
        # find relative time nearby
        time_tag = a.find_next("span")
        timestamp=None
        if time_tag:
            timestamp = parse_relative_time(time_tag.get_text(strip=True))
        if not timestamp:
            continue
        if timestamp < now - timedelta(hours=24):
            continue
        full_url = href if href.startswith("http") else "https://www.peopleperhour.com"+href
        items.append({
            "source":"peopleperhour",
            "matched_keyword":keyword,
            "title":title,
            "description":"",
            "external_id":full_url,
            "url":full_url,
            "proposal_url":full_url,
            "original_url":full_url,
            "budget_min":None,
            "budget_max":None,
            "original_currency":None,
            "currency":None,
            "affiliate":False,
            "time_submitted":timestamp.isoformat()
        })
    return items

def fetch_search(keyword: str):
    url = f"https://www.peopleperhour.com/freelance-jobs?q={keyword}"
    return fetch_from_page(url, keyword)

def get_items(keywords):
    seen=set()
    out=[]
    for kw in keywords:
        kl = kw.lower()
        if kl in CATEGORY_MAP:
            for it in fetch_from_page(CATEGORY_MAP[kl], kl):
                if it["external_id"] not in seen:
                    seen.add(it["external_id"])
                    out.append(it)
        for it in fetch_search(kl):
            if it["external_id"] not in seen:
                seen.add(it["external_id"])
                out.append(it)
    return out
