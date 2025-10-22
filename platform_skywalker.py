import logging, time
import httpx, feedparser

log = logging.getLogger("skywalker")

FEED_URL = "https://www.skywalker.gr/jobs/feed"

def _fetch_feed_text(url: str) -> str:
    try:
        with httpx.Client(timeout=25) as c:
            r = c.get(url, headers={"User-Agent":"Mozilla/5.0"})
            r.raise_for_status()
            # feedparser δέχεται string/bytes – ΟΧΙ list
            return r.text
    except Exception as e:
        log.warning("Skywalker HTTP error: %s", e)
        return ""

def fetch_skywalker_jobs(keywords):
    """Return list of jobs filtered by keywords with robust parsing."""
    try:
        url = FEED_URL[0] if isinstance(FEED_URL, list) else FEED_URL
        text = _fetch_feed_text(url)
        if not text:
            return []
        feed = feedparser.parse(text)
    except Exception as e:
        log.warning("Skywalker fetch error: %s", e)
        return []

    kws = [k.strip().lower() for k in (keywords or []) if k and k.strip()]
    out = []
    now = int(time.time())
    for e in feed.entries:
        title = e.get("title", "") or ""
        desc  = e.get("summary", "") or ""
        link  = e.get("link", "") or ""
        hay = f"{title}\n{desc}".lower()

        matched = None
        for k in kws:
            if k in hay:
                matched = k; break
        if kws and not matched:
            continue

        out.append({
            "title": title.strip() or "(untitled)",
            "description": desc.strip(),
            "original_url": link,
            "budget_min": None,
            "budget_max": None,
            "budget_currency": None,
            "source": "Skywalker",
            "time_submitted": now,
            "matched_keyword": matched,
        })
    log.info("Skywalker parsed %d entries", len(out))
    return out
