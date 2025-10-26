import httpx, time, logging

PPH_FEED_URL = "https://www.peopleperhour.com/freelance-jobs/rss"
HEADERS = {"User-Agent": "Mozilla/5.0 (PPHFeedBot)"}
log = logging.getLogger("pph")

def fetch_pph_jobs(keywords):
    """Fetch PeoplePerHour jobs with keyword filtering (sync)."""
    jobs = []
    for kw in [k.strip() for k in keywords if k.strip()]:
        try:
            with httpx.Client(timeout=15.0, headers=HEADERS) as cli:
                r = cli.get(PPH_FEED_URL, params={"q": kw})
                if r.status_code != 200:
                    continue
                txt = r.text.lower()
                if kw.lower() not in txt:
                    continue

                jobs.append({
                    "title": f"PeoplePerHour Job for '{kw}'",
                    "description": "Matched job from PeoplePerHour RSS",
                    "budget_min": None,
                    "budget_max": None,
                    "budget_currency": "GBP",
                    "original_url": PPH_FEED_URL,
                    "time_submitted": int(time.time()),
                    "matched_keyword": kw,
                    "source": "PeoplePerHour",
                })
        except Exception as e:
            log.warning("[PPH fetch error] %s", e)
    log.info("[PPH] total fetched: %d", len(jobs))
    return jobs
