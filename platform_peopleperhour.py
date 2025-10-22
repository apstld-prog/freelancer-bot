import httpx, time
from bs4 import BeautifulSoup
import logging

log = logging.getLogger("platform_peopleperhour")

PROXY_URL = "https://pph-proxy-service.onrender.com/api/pph"
HEADERS = {"User-Agent": "Mozilla/5.0"}

def fetch_pph_jobs(keywords):
    """Fetch PeoplePerHour jobs via proxy + fallback HTML."""
    all_jobs = []
    for kw in keywords:
        kw = kw.strip()
        if not kw:
            continue
        try:
            # 1️⃣ Proxy API
            proxy_url = f"{PROXY_URL}?key=1211&q={kw}"
            r = httpx.get(proxy_url, timeout=25, headers=HEADERS)
            if r.status_code == 200:
                js = r.json()
                if isinstance(js, list) and js:
                    for j in js:
                        all_jobs.append({
                            "title": j.get("title"),
                            "description": j.get("description"),
                            "budget_min": j.get("budget_min"),
                            "budget_max": j.get("budget_max"),
                            "budget_currency": j.get("budget_currency", "GBP"),
                            "original_url": j.get("url"),
                            "source": "PeoplePerHour",
                            "time_submitted": j.get("time_submitted") or int(time.time()),
                            "matched_keyword": kw,
                        })
                    continue

            # 2️⃣ Fallback HTML scraper
            html_url = f"https://www.peopleperhour.com/freelance-jobs?q={kw}"
            resp = httpx.get(html_url, timeout=25, headers=HEADERS)
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("section[data-project-id]")

            for c in cards:
                title_el = c.select_one("h5 a")
                desc_el = c.select_one("p.description")
                budget_el = c.select_one("strong.price")

                all_jobs.append({
                    "title": title_el.text.strip() if title_el else "(no title)",
                    "description": desc_el.text.strip() if desc_el else "",
                    "budget_min": None,
                    "budget_max": None,
                    "budget_currency": "GBP",
                    "original_url": f"https://www.peopleperhour.com{title_el['href']}" if title_el else "",
                    "source": "PeoplePerHour",
                    "time_submitted": int(time.time()),
                    "matched_keyword": kw,
                })

            time.sleep(1.5)
        except Exception as e:
            log.warning(f"[PPH fetch error] {e}")

    log.info(f"PPH total merged: {len(all_jobs)}")
    return all_jobs
