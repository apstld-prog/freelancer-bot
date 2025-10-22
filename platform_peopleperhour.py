# platform_peopleperhour.py — Cached & Safe unified fetch
import os, time, json, re, httpx, logging
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

log = logging.getLogger("platform_peopleperhour")

API_KEY = os.getenv("PPH_API_KEY", "1211")
PROXY_URL = os.getenv("PPH_PROXY_URL", "https://pph-proxy-service.onrender.com/api/pph")
CACHE_FILE = "pph_cache.json"
CACHE_TTL = 3600  # 1 hour cache
SAFE_DELAY = float(os.getenv("PPH_DELAY", "2.5"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PPHBot/1.1; +https://t.me/Freelancer_Alert_Jobs_bot)"
}

# ---------------- Helpers ----------------
def _load_cache():
    try:
        if not os.path.exists(CACHE_FILE):
            return {}
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_cache(cache):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except Exception:
        pass

def _cache_valid(entry):
    try:
        ts = entry.get("timestamp")
        if not ts:
            return False
        dt = datetime.fromisoformat(ts)
        age = (datetime.now(timezone.utc) - dt).total_seconds()
        return age < CACHE_TTL
    except Exception:
        return False

def _to_float(v):
    try:
        return float(re.sub(r"[^\d.]", "", str(v)))
    except Exception:
        return None

def _parse_budget(txt):
    if not txt:
        return None, None, None
    m = re.findall(r"([£$€])\s*([\d.,]+)", txt)
    if not m:
        return None, None, None
    cur_map = {"£": "GBP", "$": "USD", "€": "EUR"}
    nums = [_to_float(x[1]) for x in m if _to_float(x[1])]
    ccy = cur_map.get(m[0][0], "GBP")
    if len(nums) == 1:
        return nums[0], nums[0], ccy
    return min(nums), max(nums), ccy

# ---------------- Proxy fetch ----------------
def _fetch_via_proxy(keyword):
    try:
        url = f"{PROXY_URL}?key={API_KEY}&q={keyword}"
        r = httpx.get(url, timeout=25)
        if r.status_code != 200:
            log.warning("PPH proxy %s for %s", r.status_code, keyword)
            return []
        data = r.json()
        if isinstance(data, dict) and "results" in data:
            data = data["results"]
        if not isinstance(data, list):
            return []
        items = []
        for it in data:
            items.append({
                "title": it.get("title", "").strip(),
                "description": it.get("description", "").strip(),
                "original_url": it.get("url") or it.get("original_url") or "",
                "budget_min": it.get("budget_min"),
                "budget_max": it.get("budget_max"),
                "budget_currency": it.get("budget_currency") or "GBP",
                "source": "PeoplePerHour",
                "time_submitted": it.get("time_submitted") or datetime.now(timezone.utc).isoformat(),
                "matched_keyword": keyword,
            })
        log.info("PPH proxy %d results for '%s'", len(items), keyword)
        return items
    except Exception as e:
        log.warning("PPH proxy error for %s: %s", keyword, e)
        return []

# ---------------- Fallback scraper ----------------
def _fetch_html(keyword):
    try:
        url = f"https://www.peopleperhour.com/freelance-jobs?q={keyword}"
        r = httpx.get(url, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            log.warning("PPH HTML %s for %s", r.status_code, keyword)
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select("section[data-project-id], li[data-project-id]")
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
        log.info("PPH HTML scraped %d for '%s'", len(items), keyword)
        return items
    except Exception as e:
        log.warning("PPH HTML error for %s: %s", keyword, e)
        return []

# ---------------- Unified get_items ----------------
def get_items(keywords):
    cache = _load_cache()
    all_items = []

    for kw in keywords:
        kw = kw.strip()
        if not kw:
            continue

        # Cache check
        entry = cache.get(kw)
        if entry and _cache_valid(entry):
            log.info("PPH cache hit '%s' (%d cached)", kw, len(entry.get("items", [])))
            all_items.extend(entry["items"])
            continue

        log.info("Fetching PPH for keyword '%s'...", kw)
        items = _fetch_via_proxy(kw)
        if not items:
            log.info("PPH proxy empty for '%s' → fallback HTML", kw)
            items = _fetch_html(kw)

        cache[kw] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "items": items,
            "count": len(items)
        }
        _save_cache(cache)

        all_items.extend(items)
        time.sleep(SAFE_DELAY)

    log.info("PPH total merged: %d", len(all_items))
    return all_items
