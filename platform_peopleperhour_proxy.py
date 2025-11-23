import httpx
import logging
from urllib.parse import urlencode

log = logging.getLogger("pph")

PPH_BASE = "https://pph-proxy.onrender.com"

AFFILIATE_PREFIX = "https://www.peopleperhour.com/site/signup?rfrd=xxxx&"  # βάλε το δικό σου αν έχεις

def _wrap_affiliate(url: str) -> str:
    try:
        return AFFILIATE_PREFIX + urlencode({"goto": url})
    except:
        return url

def _normalize_budget(budget):
    if not budget:
        return (None, None, None)
    try:
        amount = float(budget.get("amount", 0))
        currency = budget.get("currency", "USD")
        return (amount, amount, currency)
    except:
        return (None, None, None)


def get_items(keywords: list):
    """
    Fetch PeoplePerHour jobs from proxy: https://pph-proxy.onrender.com/jobs
    Returns list of dict items with unified format.
    """

    url = f"{PPH_BASE}/jobs"
    try:
        res = httpx.get(url, timeout=20)
        if res.status_code != 200:
            log.warning(f"PPH proxy bad status {res.status_code}")
            return []

        data = res.json()
        if not isinstance(data, list):
            log.warning("PPH proxy returned non-list")
            return []

    except Exception as e:
        log.error(f"PPH proxy error: {e}")
        return []

    out = []
    for job in data:
        title = job.get("title", "")
        url = job.get("url", "")

        # match by keyword
        matched = None
        low_title = title.lower()
        for kw in keywords:
            if kw.lower() in low_title:
                matched = kw
                break
        if not matched:
            continue

        min_b, max_b, curr = _normalize_budget(job.get("budget"))

        item = {
            "source": "PeoplePerHour",
            "matched_keyword": matched,
            "title": title,
            "url": url,
            "affiliate_url": _wrap_affiliate(url),
            "budget_min": min_b,
            "budget_max": max_b,
            "original_currency": curr,
            "posted": job.get("posted"),
        }
        out.append(item)

    return out
