import logging, time, httpx, feedparser

log = logging.getLogger("skywalker")
FEED_URL = "https://www.skywalker.gr/jobs/feed"

def _detect_currency(text: str) -> str:
    """Smart currency detection for Skywalker listings."""
    if not text:
        return "EUR"
    t = text.lower()
    if "€" in t or "eur" in t or "ευρώ" in t:
        return "EUR"
    if "£" in t or "gbp" in t or "pound" in t:
        return "GBP"
    if "$" in t or "usd" in t or "dollar" in t:
        return "USD"
    if "₹" in t or "inr" in t or "rupee" in t:
        return "INR"
    return "EUR"

def fetch_skywalker_jobs(keywords):
    """Fetch Skywalker RSS feed with keyword filtering and currency detection."""
    try:
        url = FEED_URL[0] if isinstance(FEED_URL, list) else FEED_URL
        txt = httpx.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0"}).text
        if not txt:
            log.warning("Skywalker feed empty")
            return []
        feed = feedparser.parse(txt)
    except Exception as e:
        log.warning("Skywalker fetch error: %s", e)
        return []

    kws = [k.strip().lower() for k in (keywords or []) if k and k.strip()]
    out = []
    now = int(time.time())
    for e in feed.entries:
        title = e.get("title", "") or ""
        desc = e.get("summary", "") or ""
        link = e.get("link", "") or ""
        hay = f"{title}\n{desc}".lower()

        matched = None
        for k in kws:
            if k in hay:
                matched = k
                break
        if kws and not matched:
            continue

        currency = _detect_currency(hay)

        out.append({
            "title": title.strip() or "(untitled)",
            "description": desc.strip(),
            "original_url": link,
            "budget_min": None,
            "budget_max": None,
            "budget_currency": currency,
            "source": "Skywalker",
            "time_submitted": now,
            "matched_keyword": matched,
        })
    log.info("Skywalker parsed %d entries", len(out))
    return out
