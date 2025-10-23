import httpx, time, logging
from bs4 import BeautifulSoup

log = logging.getLogger("platform_peopleperhour")

PROXY_URL = "https://pph-proxy-service.onrender.com/api/pph"
HEADERS = {"User-Agent": "Mozilla/5.0"}

def _detect_currency_pph(entry: dict) -> str:
    """Try to detect the correct currency code for PeoplePerHour listings."""
    cur = entry.get("budget_currency")
    if cur and isinstance(cur, str) and len(cur) == 3:
        return cur.upper()

    # fallback from symbols or text
    txt = f"{entry.get('budget_min', '')} {entry.get('budget_max', '')}".lower()
    if "€" in txt:
        return "EUR"
    if "£" in txt:
        return "GBP"
    if "$" in txt:
        return "USD"
    return "GBP"  # default fallback (PPH uses GBP most often)

def fetch_pph_jobs(keywords):
    """Fetch PeoplePerHour jobs via proxy + fallback HTML."""
    all_jobs = []
    for kw in [k.strip() for k in keywords if k.strip()]:
        try:
            # 1️⃣ Try proxy
            proxy_url = f"{PROXY_URL}?key=1211&q={kw}"
            r = httpx.get(proxy_url, timeout=25, headers=HEADERS)
            if r.status_code == 200:
                js = r.json()
                if isinstance(js, list) and js:
                    for j in js:
                        cur = _detect_currency_pph(j)
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

            # 2️⃣ HTML fallback
            html_url = f"https://www.peopleperhour.com/freelance-jobs?q={kw}"
            resp = httpx.get(html_url, timeout=25, headers=HEADERS)
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("li[data-project-id]")

            for c in cards:
                title_el = c.select_one("h5 a, h3 a")
                desc_el = c.select_one("p.truncated, p.description")
                budget_el = c.select_one("span.value")
                cur = "GBP"
                if budget_el:
                    val = budget_el.text
                    if "€" in val:
                        cur = "EUR"
                    elif "$" in val:
                        cur = "USD"
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
