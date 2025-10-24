import httpx
import logging
from datetime import datetime, timezone
from bs4 import BeautifulSoup

log = logging.getLogger("skywalker")

SKYWALKER_FEED_URL = "https://www.skywalker.gr/jobs/feed"

async def fetch_skywalker_jobs(keywords=None):
    """Fetch jobs from Skywalker RSS feed (ignores keywords for now)."""
    jobs = []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(SKYWALKER_FEED_URL)
            if r.status_code == 200:
                # ✅ Try xml parser, fallback to html.parser if unavailable
                try:
                    soup = BeautifulSoup(r.text, "xml")
                except Exception:
                    soup = BeautifulSoup(r.text, "html.parser")

                items = soup.find_all("item")
                log.info(f"Skywalker parsed {len(items)} entries")

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
            else:
                log.warning(f"[Skywalker] status {r.status_code}")
    except Exception as e:
        log.warning(f"Skywalker error: {e}")
    return jobs
