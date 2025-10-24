import httpx, time, logging
from bs4 import BeautifulSoup

log = logging.getLogger("platform_peopleperhour")

PROXY_URL = "https://pph-proxy-service.onrender.com/api/pph"
HEADERS = {"User-Agent": "Mozilla/5.0"}

def _detect_currency(text: str) -> str:
    """Smart currency detection for PeoplePerHour listings."""
    if not text:
        return "GBP"
    t = text.lower()
    if "€" in t or "eur" in t or "euro" in t:
        return "EUR"
    if "£" in t or "gbp" in t or "pound" in t:
        return "GBP"
    if "₹" in t or "inr" in t or "rupee" in t:
        return "INR"
    if "aud" in t or "a$" in t or "australian" in t:
        return "AUD"
    if "cad" in t or "c$" in t or "canadian" in t:
        return "CAD"
    if "php" in t or "peso" in t:
        return "PHP"
    if "$" in t or "usd" in t or "dollar" in t:
        return "USD"
    return "GBP"  # default fallback

def fetch_pph_jobs(keywords):
    """Fetch PeoplePerHour jobs via proxy + fallback HTML with currency detection."""
    all_jobs = []
    for kw in [k.strip() for k in keywords if k.strip()]:
        try:
            # Try proxy JSON API
            proxy_url = f"{PROXY_URL}?key=1211&q={kw}"
            r = httpx.get(proxy_url, timeout=25, headers=HEADERS)
            if r.status_code == 200:
                js = r.json()
                if isinstance(js, list) and js:
                    for j in js:
                        cur = j.get("budget_currency") or _detect_currency(str(j))
                        all_jobs.append({
                            "title": j.get("title"),
                            "description": j.get("description"),
                            "budget_min": j.get("budget_min"),
                            "budget_max": j.get("budget_max"),
                            "budget_currency": cur,
                            "original_url": j.get("url"),
                            "source": "PeoplePerHour",
                            "time_submitted": j.get("time_submitted") or int(time.time()),
                            "matched_keyword": kw,
                        })
                    continue

            # HTML fallback
            html_url = f"https://www.peopleperhour.com/freelance-jobs?q={kw}"
            resp = httpx.get(html_url, timeout=25, headers=HEADERS)
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("li[data-project-id]")

            for c in cards:
                title_el = c.select_one("h5 a, h3 a")
                desc_el = c.select_one("p.truncated, p.description")
                budget_el = c.select_one("span.value")
                budget_text = budget_el.text if budget_el else ""
                cur = _detect_currency(budget_text)
                all_jobs.append({
                    "title": title_el.text.strip() if title_el else "(no title)",
                    "description": desc_el.text.strip() if desc_el else "",
                    "budget_min": None,
                    "budget_max": None,
                    "budget_currency": cur,
                    "original_url": f"https://www.peopleperhour.com{title_el['href']}" if title_el else "",
                    "source": "PeoplePerHour",
                    "time_submitted": int(time.time()),
                    "matched_keyword": kw,
                })
            time.sleep(1.5)
        except Exception as e:
            log.warning(f"[PPH fetch error] {e}")

    log.info(f"[PPH total merged: {len(all_jobs)}]")
    return all_jobs
