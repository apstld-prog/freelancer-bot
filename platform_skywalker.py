import httpx
import logging
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

log = logging.getLogger("skywalker")

BASE_URL = "https://www.skywalker.gr/el/thesis-ergasias"

def parse_skywalker_date(date_text: str):
    """Μετατροπή ελληνικών ημερομηνιών σε datetime"""
    try:
        # Συνήθεις μορφές: "24 Οκτ 2025" ή "Σήμερα", "Χθες"
        date_text = date_text.strip().lower()
        now = datetime.now(tz=timezone.utc)
        months = {
            "ιαν": 1, "φεβ": 2, "μαρ": 3, "απρ": 4,
            "μαι": 5, "ιουν": 6, "ιουλ": 7, "αυγ": 8,
            "σεπ": 9, "οκτ": 10, "νοε": 11, "δεκ": 12
        }

        if "σήμερα" in date_text:
            return now
        if "χθες" in date_text:
            return now - timedelta(days=1)

        parts = date_text.replace(",", "").split()
        if len(parts) >= 3:
            day = int(parts[0])
            month = months.get(parts[1][:3], now.month)
            year = int(parts[2])
            return datetime(year, month, day, tzinfo=timezone.utc)

    except Exception:
        pass
    return datetime.now(tz=timezone.utc)

async def fetch_skywalker_jobs(keywords):
    """Αναζήτηση αγγελιών απευθείας από τη σελίδα Skywalker."""
    jobs = []
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            log.info(f"[Skywalker] Fetching {BASE_URL}")
            r = await client.get(BASE_URL)
            if r.status_code != 200:
                log.warning(f"[Skywalker] Status {r.status_code}")
                return []

            soup = BeautifulSoup(r.text, "html.parser")

            # Επιλογή αγγελιών (2025 layout)
            job_cards = soup.select("article.job, div.job-item, div.job-list-item")
            log.info(f"[Skywalker] Found {len(job_cards)} raw listings")

            for card in job_cards:
                try:
                    # Τίτλος
                    title_tag = card.find("a")
                    title = title_tag.text.strip() if title_tag else ""
                    link = title_tag["href"] if title_tag and title_tag.get("href") else ""
                    if link and not link.startswith("http"):
                        link = f"https://www.skywalker.gr{link}"

                    # Περιγραφή
                    desc_tag = card.find("p") or card.find("div", class_="desc")
                    desc = desc_tag.text.strip() if desc_tag else ""
                    desc = desc[:400]

                    # Ημερομηνία δημοσίευσης
                    date_tag = card.find("span", class_="date") or card.find("div", class_="job-date")
                    date_text = date_tag.text.strip() if date_tag else "σήμερα"
                    dt = parse_skywalker_date(date_text)

                    # Φιλτράρισμα 48 ωρών
                    if dt < datetime.now(tz=timezone.utc) - timedelta(hours=48):
                        continue

                    # Ταίριασμα με keywords
                    text_to_match = (title + " " + desc).lower()
                    if not any(k.lower() in text_to_match for k in keywords):
                        continue

                    jobs.append({
                        "title": title,
                        "description": desc,
                        "original_url": link,
                        "affiliate_url": link,
                        "budget_amount": None,
                        "budget_currency": "",
                        "source": "Skywalker",
                        "timestamp": dt.timestamp()
                    })

                except Exception as e:
                    log.warning(f"[Skywalker parse error] {e}")

    except Exception as e:
        log.warning(f"[Skywalker error] {e}")

    log.info(f"[Skywalker parsed {len(jobs)} entries after filtering]")
    return jobs
