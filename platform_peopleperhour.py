import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from currency_usd import convert_to_usd

logger = logging.getLogger("platform_peopleperhour")


def _parse_budget(text: str):
    """Extract min/max/avg and currency from text like '£50 – £150 GBP'."""
    if not text:
        return None, None, None, None
    import re
    clean = text.replace(",", "").replace("–", "-").strip()
    m = re.findall(r"([£$€]?)(\d+(?:\.\d+)?)", clean)
    if not m:
        return None, None, None, None
    values = [float(v[1]) for v in m]
    currency_symbol = m[0][0]
    cur = "GBP"
    if currency_symbol == "$":
        cur = "USD"
    elif currency_symbol == "€":
        cur = "EUR"
    if len(values) == 1:
        return values[0], values[0], values[0], cur
    return values[0], values[-1], sum(values) / len(values), cur


def _parse_relative_time(txt: str):
    """Convert '3 hours ago' or '2 days ago' → datetime (UTC)."""
    if not txt:
        return datetime.now(timezone.utc)
    txt = txt.lower()
    now = datetime.now(timezone.utc)
    import re
    m = re.search(r"(\d+)\s+(minute|hour|day)", txt)
    if not m:
        return now
    num = int(m.group(1))
    unit = m.group(2)
    if "minute" in unit:
        return now - timedelta(minutes=num)
    if "hour" in unit:
        return now - timedelta(hours=num)
    if "day" in unit:
        return now - timedelta(days=num)
    return now


def fetch_pph_jobs(keywords):
    """
    Scrape PeoplePerHour jobs feed and return list of dicts with:
    title, description, url, budget_min/max/avg, currency, usd, created_at, posted_ago, matched_keyword
    """
    results = []
    if not keywords:
        return results

    try:
        for kw in keywords:
            url = f"https://www.peopleperhour.com/freelance-jobs/search?query={kw}"
            logger.info(f"[PPH] Fetching keyword: {kw}")
            r = httpx.get(url, timeout=30, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                logger.warning(f"[PPH] HTTP {r.status_code} for keyword {kw}")
                continue

            soup = BeautifulSoup(r.text, "html.parser")
            cards = soup.select("section.listing-card, div.project")
            for card in cards:
                title_el = card.select_one("h3, h2")
                title = title_el.get_text(strip=True) if title_el else "(no title)"

                desc_el = card.select_one("p, div.description, div.project__desc")
                desc = desc_el.get_text(strip=True) if desc_el else ""

                href = card.select_one("a[href]")
                link = "https://www.peopleperhour.com" + href["href"] if href and href["href"].startswith("/") else (href["href"] if href else "")

                budget_el = card.select_one(".listing-card__price, .project__price, .price")
                budget_txt = budget_el.get_text(strip=True) if budget_el else ""
                bmin, bmax, bavg, cur = _parse_budget(budget_txt)
                usd_val = convert_to_usd(bavg, cur) if bavg else None

                time_el = card.select_one(".listing-card__time, time")
                time_txt = time_el.get_text(strip=True) if time_el else ""
                created_at = _parse_relative_time(time_txt)

                results.append({
                    "platform": "peopleperhour",
                    "title": title,
                    "description": desc,
                    "original_url": link,
                    "budget_min": bmin,
                    "budget_max": bmax,
                    "budget_amount": bavg,
                    "budget_currency": cur,
                    "budget_usd": usd_val,
                    "created_at": created_at,
                    "posted_ago": time_txt or "N/A",
                    "matched_keyword": kw,
                })

        logger.info(f"[PPH] ✅ {len(results)} jobs fetched")
        return results

    except Exception as e:
        logger.exception(f"[PPH] Error: {e}")
        return []
