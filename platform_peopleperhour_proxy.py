# platform_peopleperhour_proxy.py — FINAL VERSION
import httpx
import logging
from urllib.parse import urlencode

log = logging.getLogger("pph")

PPH_BASE = "https://pph-proxy.onrender.com"

AFFILIATE_PREFIX = ""  # βάλε affiliate αν θέλεις, αλλιώς άστο κενό

def _wrap_affiliate(url: str) -> str:
    try:
        return AFFILIATE_PREFIX + urlencode({"goto": url})
    except:
        return url

def _normalize_budget(job):
    if not job:
        return None, None, None
    b = job.get("budget")
    if not b:
        return None, None, None
    try:
        amount = float(b.get("amount"))
        curr = b.get("currency", "USD")
        return amount, amount, curr
    except:
        return None, None, None

def get_items(keywords: list):
    url = f"{PPH_BASE}/jobs"
    try:
        res = httpx.get(url, timeout=20)
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        log.error(f"PPH proxy error: {e}")
        return []

    if not isinstance(data, list):
        log.error("PPH proxy returned non-list JSON.")
        return []

    out = []

    for job in data:
        title = (job.get("title") or "").strip()
        url = job.get("url") or ""

        if not title or not url:
            continue

        low_title = title.lower()
        matched = None
        for kw in keywords:
            if kw.lower() in low_title:
                matched = kw
                break
        if not matched:
            continue

        bmin, bmax, curr = _normalize_budget(job)

        item = {
            "source": "PeoplePerHour",
            "matched_keyword": matched,
            "title": title,
            "url": url,
            "affiliate_url": _wrap_affiliate(url),
            "budget_min": bmin,
            "budget_max": bmax,
            "original_currency": curr,
            "posted": job.get("posted"),
        }

        out.append(item)

    return out
