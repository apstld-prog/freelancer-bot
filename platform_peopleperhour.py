import os, re, json, time, logging, random
import httpx
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

log = logging.getLogger("peopleperhour")

API_BASE = "https://pph-proxy-service.onrender.com/api/pph"
API_KEY = os.getenv("API_KEY", "1211")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)

HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json, text/html"}

# Convert textual "x hours ago" to datetime UTC
def _parse_relative_time(txt: str) -> datetime | None:
    try:
        txt = txt.strip().lower()
        if "minute" in txt:
            n = int(re.findall(r"(\d+)", txt)[0])
            return datetime.now(timezone.utc) - timedelta(minutes=n)
        if "hour" in txt:
            n = int(re.findall(r"(\d+)", txt)[0])
            return datetime.now(timezone.utc) - timedelta(hours=n)
        if "day" in txt:
            n = int(re.findall(r"(\d+)", txt)[0])
            return datetime.now(timezone.utc) - timedelta(days=n)
    except Exception:
        return None
    return None


def fetch_peopleperhour(keyword: str) -> list[dict]:
    """Fetch jobs from proxy or fallback scrape."""
    jobs: list[dict] = []
    keyword_q = keyword.strip().replace(" ", "+")
    url = f"{API_BASE}?key={API_KEY}&q={keyword_q}"

    try:
        with httpx.Client(timeout=20, headers=HEADERS) as client:
            r = client.get(url)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    for j in data:
                        title = j.get("title") or ""
                        desc = j.get("description") or ""
                        bmin = j.get("budget_min")
                        bmax = j.get("budget_max")
                        cur = j.get("budget_currency") or "GBP"
                        orig = j.get("original_url")
                        ts = j.get("time_submitted")
                        if ts:
                            try:
                                ts_dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
                            except Exception:
                                ts_dt = datetime.now(timezone.utc)
                        else:
                            ts_dt = datetime.now(timezone.utc)

                        jobs.append({
                            "title": title.strip(),
                            "description": desc.strip(),
                            "budget_amount": f"{bmin}-{bmax}" if bmin and bmax else str(bmin or ""),
                            "budget_currency": cur,
                            "original_url": orig,
                            "source": "PeoplePerHour",
                            "time_submitted": ts_dt,
                        })
                    if jobs:
                        log.info(f"PPH proxy returned {len(jobs)} jobs for '{keyword}'")
                        return jobs
    except Exception as e:
        log.warning(f"PPH proxy failed: {e}")

    # Fallback scraping
    log.warning("PPH fallback scraping for '%s'", keyword)
    try:
        html_url = f"https://www.peopleperhour.com/freelance-jobs?q={keyword_q}"
        with httpx.Client(timeout=25, headers=HEADERS) as client:
            r = client.get(html_url)
        if r.status_code != 200:
            log.warning("PPH fallback HTTP %d", r.status_code)
            return jobs

        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select("section.project-tile")
        for card in cards:
            try:
                title_el = card.select_one("h5 a")
                title = title_el.text.strip() if title_el else "(No title)"
                href = "https://www.peopleperhour.com" + title_el["href"] if title_el else ""
                desc_el = card.select_one(".description")
                desc = desc_el.text.strip() if desc_el else ""
                budget_el = card.select_one(".budget")
                budget_txt = budget_el.text.strip() if budget_el else ""
                match = re.search(r"(\d+)[^\d]+(\d+)?\s*([A-Z]{3})", budget_txt)
                if match:
                    bmin = match.group(1)
                    bmax = match.group(2) or bmin
                    cur = match.group(3)
                else:
                    bmin, bmax, cur = "", "", "GBP"

                time_el = card.select_one(".time")
                ttxt = time_el.text.strip() if time_el else ""
                ts_dt = _parse_relative_time(ttxt) or datetime.now(timezone.utc)

                jobs.append({
                    "title": title,
                    "description": desc,
                    "budget_amount": f"{bmin}-{bmax}" if bmin else "",
                    "budget_currency": cur,
                    "original_url": href,
                    "source": "PeoplePerHour",
                    "time_submitted": ts_dt,
                })
            except Exception as e:
                log.debug("PPH parse card error: %s", e)

        log.info(f"PPH scraped {len(jobs)} jobs for '{keyword}'")
        time.sleep(random.uniform(1, 2))
    except Exception as e:
        log.error(f"PPH scraping failed: {e}")

    return jobs
