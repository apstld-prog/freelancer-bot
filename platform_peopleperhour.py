# platform_peopleperhour.py — FINAL
import os, requests, time, re
from bs4 import BeautifulSoup

API_KEY = os.getenv("PPH_API_KEY", "1211")
PROXY_URL = f"https://pph-proxy-service.onrender.com/api/pph?key={API_KEY}"
BASE_URL = "https://www.peopleperhour.com/freelance-jobs"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Bot/1.0)"}

def _parse_price(txt: str):
    if not txt:
        return None, None, None
    txt = txt.replace(",", "").replace("–", "-").strip()
    m = re.findall(r"([\d\.]+)", txt)
    cur = "GBP" if "£" in txt else "USD" if "$" in txt else "EUR" if "€" in txt else None
    if not m:
        return None, None, cur
    vals = [float(v) for v in m]
    if len(vals) == 1:
        return vals[0], None, cur
    return min(vals), max(vals), cur

def _fetch_via_proxy(q: str):
    try:
        resp = requests.get(f"{PROXY_URL}&q={q}", timeout=15)
        if resp.status_code == 200:
            js = resp.json()
            if isinstance(js, list):
                return js
    except Exception:
        pass
    return []

def _fetch_direct(q: str):
    """Fallback direct scrape from PPH site"""
    url = f"{BASE_URL}?q={q}"
    r = requests.get(url, headers=HEADERS, timeout=15)
    if r.status_code != 200:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    cards = soup.select("section.JobSearchCard")
    out = []
    for c in cards:
        title_el = c.select_one("a.JobSearchCard-primary-heading-link")
        desc_el = c.select_one("p.JobSearchCard-primary-description")
        budget_el = c.select_one("div.JobSearchCard-secondary-price")
        if not title_el:
            continue
        title = title_el.text.strip()
        desc = (desc_el.text.strip() if desc_el else "")
        budget_min, budget_max, budget_currency = _parse_price(budget_el.text if budget_el else "")
        link = title_el.get("href", "")
        if link and not link.startswith("http"):
            link = "https://www.peopleperhour.com" + link
        out.append({
            "title": title,
            "description": desc,
            "budget_min": budget_min,
            "budget_max": budget_max,
            "budget_currency": budget_currency,
            "original_url": link,
            "source": "PeoplePerHour",
            "time_submitted": int(time.time())
        })
    return out

def get_items(keywords: list[str]):
    all_items = []
    for kw in keywords or ["freelance"]:
        kw = kw.strip()
        if not kw:
            continue
        data = _fetch_via_proxy(kw)
        if not data:
            data = _fetch_direct(kw)
        for it in data:
            if not isinstance(it, dict):
                continue
            it.setdefault("source", "PeoplePerHour")
            it.setdefault("time_submitted", int(time.time()))
        all_items.extend(data)
        time.sleep(2)
    return all_items
