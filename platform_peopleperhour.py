# platform_peopleperhour.py — unified proxy + fallback scraper (safe version)
import os, time, logging, re, json, httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

log = logging.getLogger("platform_peopleperhour")

API_KEY = os.getenv("PPH_API_KEY", "1211")
PROXY_URL = os.getenv("PPH_PROXY_URL", "https://pph-proxy-service.onrender.com/api/pph")
SAFE_DELAY = float(os.getenv("PPH_DELAY", "2.5"))  # seconds between keywords

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PPHBot/1.0; +https://t.me/Freelancer_Alert_Jobs_bot)"
}

def _to_float(v):
    try:
        return float(re.sub(r"[^\d.]", "", str(v)))
    except Exception:
        return None

def _parse_budget(text):
    """
    Extract min/max/currency from a text like '£50 - £120' or '$100'
    """
    if not text:
        return None, None, None
    text = text.strip()
    m = re.findall(r"([£$€])\s*([\d.,]+)", text)
    if not m:
        return None, None, None
    curr_map = {"£": "GBP", "$": "USD", "€": "EUR"}
    nums = [_to_float(x[1]) for x in m if _to_float(x[1])]
    ccy = curr_map.get(m[0][0], "USD")
    if len(nums) == 1:
        return nums[0], nums[0], ccy
    elif len(nums) >= 2:
        return min(nums), max(nums), ccy
    return None, None, ccy

def _to_dt_from_now(minutes_ago):
    try:
        return datetime.now(timezone.utc) - timedelta(minutes=int(minutes_ago))
    except Exception:
        return datetime.now(timezone.utc)

# ---------------------------------------
# 1️⃣ Try fetching via proxy first
# ---------------------------------------
def _fetch_via_proxy(keyword: str):
    try:
        url = f"{PROXY_URL}?key={API_KEY}&q={keyword}"
        r = httpx.get(url, timeout=20)
        if r.status_code != 200:
            log.warning("PPH proxy returned %s for %s", r.status_code, keyword)
            return []
        data = r.json()
        if isinstance(data, dict) and "results" in data:
            data = data["results"]
        if not isinstance(data, list):
            log.debug("Proxy JSON not list: %s", str(data)[:200])
            return []
        items = []
        for it in data:
            title = it.get("title") or ""
            desc = it.get("description") or ""
            url = it.get("url") or it.get("original_url") or ""
            bmin = it.get("budget_min")
            bmax = it.get("budget_max")
            cur = it.get("budget_currency") or "GBP"
            dt = it.get("time_submitted") or datetime.now(timezone.utc).isoformat()
            items.append({
                "title": title.strip(),
                "description": desc.strip(),
                "original_url": url.strip(),
                "budget_min": bmin,
                "budget_max": bmax,
                "budget_currency": cur,
                "source": "PeoplePerHour",
                "time_submitted": dt,
                "matched_keyword": keyword,
            })
        log.info("PPH proxy returned %d items for '%s'", len(items), keyword)
        return items
    except Exception as e:
        log.warning("PPH proxy error for %s: %s", keyword, e)
        return []

# ---------------------------------------
# 2️⃣ Fallback to HTML scraping
# ---------------------------------------
def _fetch_html(keyword: str):
    try:
        url = f"https://www.peopleperhour.com/freelance-jobs?q={keyword}"
        r = httpx.get(url, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            log.warning("PPH HTML status %s for %s", r.status_code, keyword)
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select("section[data-project-id]") or soup.select("li[data-project-id]")
        items = []
        for card in cards[:20]:
            title_el = card.select_one("h2, h3")
            title = title_el.get_text(strip=True) if title_el else "(untitled)"
            desc_el = card.select_one("p, div.description")
            desc = desc_el.get_text(" ", strip=True) if desc_el else ""
            budget_el = card.find(string=re.compile(r"£|\$|€"))
            bmin, bmax, ccy = _parse_budget(budget_el)
            link_el = card.select_one("a[href*='/freelance-jobs/']")
            link = "https://www.peopleperhour.com" + link_el["href"] if link_el else url
            posted = datetime.now(timezone.utc).isoformat()
            items.append({
                "title": title,
                "description": desc,
                "budget_min": bmin,
                "budget_max": bmax,
                "budget_currency": ccy,
                "original_url": link,
                "source": "PeoplePerHour",
                "time_submitted": posted,
                "matched_keyword": keyword,
            })
        log.info("PPH HTML scraped %d items for '%s'", len(items), keyword)
        return items
    except Exception as e:
        log.warning("PPH HTML error for %s: %s", keyword, e)
        return []

# ---------------------------------------
# 3️⃣ Unified public fetch
# ---------------------------------------
def get_items(keywords):
    all_items = []
    for kw in keywords:
        kw = kw.strip()
        if not kw:
            continue
        log.debug("Fetching PPH for keyword: %s", kw)
        # step 1: proxy
        res = _fetch_via_proxy(kw)
        # step 2: fallback if empty
        if not res:
            log.info("PPH proxy empty for '%s' → fallback to HTML", kw)
            res = _fetch_html(kw)
        # append to global list
        all_items.extend(res)
        time.sleep(SAFE_DELAY)
    log.info("PPH total fetched: %d", len(all_items))
    return all_items
