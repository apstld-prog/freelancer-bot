import httpx
import logging
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

log = logging.getLogger("skywalker")

SKYWALKER_FEED_URL = "https://www.skywalker.gr/jobs/feed"

async def fetch_skywalker_jobs(keywords=None):
    """Fetch jobs from Skywalker RSS feed or HTML fallback."""
    jobs = []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(SKYWALKER_FEED_URL)
            if r.status_code == 200:
                try:
                    soup = BeautifulSoup(r.text, "xml")
                    items = soup.find_all("item")
                except Exception:
                    soup = BeautifulSoup(r.text, "html.parser")
                    items = soup.find_all("item")

                # ✅ Αν το RSS είναι άδειο, δοκιμάζουμε HTML fallback
                if not items:
                    log.info("[Skywalker] RSS empty, trying HTML fallback...")
                    html = await client.get("https://www.skywalker.gr/el/thesis-ergasias")
                    hsoup = BeautifulSoup(html.text, "html.parser")
                    blocks = hsoup.find_all("div", class_="job")

                    for b in blocks:
                        title_tag = b.find("a")
                        title = title_tag.text.strip() if title_tag else ""
                        link = title_tag["href"] if title_tag and title_tag.get("href") else ""
                        link = link if link.startswith("http") else f"https://www.skywalker.gr{link}"
                        desc = (b.find("p").text.strip() if b.find("p") else "")
                        ts = datetime.now(tz=timezone.utc).timestamp()

                        job = {
                            "title": title,
                            "description": desc,
                            "original_url": link,
                            "affiliate_url": link,
                            "budget_amount": 0,
                            "budget_currency": "EUR",
                            "source": "Skywalker",
                            "timestamp": ts,
                        }
                        jobs.append(job)

                # ✅ Διαβάζουμε κανονικό RSS
                else:
                    for item in items:
                        title = item.title.text.strip() if item.title else ""
                        desc = item.description.text.strip() if item.description else ""
                        link = item.link.text.strip() if item.link else ""
                        pub_date = item.pubDate.text.strip() if item.pubDate else ""
                        ts = None
                        if pub_date:
                            try:
                                ts = datetime.strptime(pub_date, "%a, %d %b %Y %H:%M:%S %z").timestamp()
                            except Exception:
                                ts = datetime.now(tz=timezone.utc).timestamp()
                        link = str(link) if link else ""
                        job = {
                            "title": title,
                            "description": desc,
                            "original_url": link,
                            "affiliate_url": link,
                            "budget_amount": 0,
                            "budget_currency": "EUR",
                            "source": "Skywalker",
                            "timestamp": ts,
                        }
                        jobs.append(job)

                # ✅ Φιλτράρισμα λέξεων-κλειδιών
                if keywords:
                    kw_lower = [k.lower() for k in keywords]
                    jobs = [
                        j for j in jobs
                        if any(k in (j["title"].lower() + j["description"].lower()) for k in kw_lower)
                    ]

                # ✅ Μόνο αγγελίες έως 48 ωρών
                cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=48)
                jobs = [j for j in jobs if datetime.fromtimestamp(j["timestamp"], tz=timezone.utc) >= cutoff]

                log.info(f"Skywalker parsed {len(jobs)} entries after filtering")
            else:
                log.warning(f"[Skywalker] status {r.status_code}")
    except Exception as e:
        log.warning(f"Skywalker error: {e}")
    return jobs
