
# platform_peopleperhour.py — HTML parser without bs4, regex/heuristics
from typing import List, Dict, Optional, Tuple
import os, re, html, urllib.parse, logging
from datetime import datetime, timezone, timedelta
import httpx

log = logging.getLogger("pph")

FRESH_HOURS = int(os.getenv("FRESH_WINDOW_HOURS", "48"))
USER_AGENT = os.getenv("HTTP_USER_AGENT", "Mozilla/5.0 JobBot/1.6")

BASE_LIST = os.getenv("PPH_BASE_URL", "https://www.peopleperhour.com/freelance-jobs?search={kw}")
PER_KEYWORD_LIMIT = int(os.getenv("PPH_PER_KEYWORD_LIMIT", "10"))

_re_job = re.compile(r'href="(?P<href>/freelance-jobs/[^"]*?-(?P<id>\d+))"[^>]*>(?P<title>.*?)</a>', re.I|re.S)
_re_price = re.compile(r'(?:(?:Budget|Fixed|From)\s*:?\s*)?([£$€])\s?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)', re.I)
_re_strip = re.compile(r"<[^>]+>")
_re_space = re.compile(r"\s+")

def _fetch(url: str, timeout: float = 15.0) -> str:
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.text

def _abs(url: str) -> str:
    if url.startswith("http"):
        return url
    return urllib.parse.urljoin("https://www.peopleperhour.com", url)

def _clean(txt: str) -> str:
    txt = html.unescape(_re_strip.sub(" ", txt))
    return _re_space.sub(" ", txt).strip()

def _parse_listing(body: str) -> List[Dict]:
    jobs = []
    for m in _re_job.finditer(body):
        href = _abs(m.group("href"))
        title = _clean(m.group("title"))
        # Grab a small snippet around the link for budget hints
        start = max(0, m.start()-400)
        chunk = body[start:m.end()+400]
        bud = _re_price.search(chunk)
        currency = amount = None
        if bud:
            currency = {"£":"GBP","$":"USD","€":"EUR"}.get(bud.group(1), bud.group(1))
            amount = bud.group(2).replace(",", "").replace(".", "")
            try:
                amount = int(amount)
            except Exception:
                amount = None
        jobs.append({
            "title": title,
            "description": None,
            "budget_min": amount,
            "budget_max": None,
            "budget_currency": currency,
            "url": href,
            "posted_at": datetime.now(timezone.utc).isoformat(),
        })
    return jobs

def get_items(keywords: List[str], fresh_since: datetime, limit: int, logger=None) -> List[Dict]:
    logger = logger or log
    out: List[Dict] = []
    for kw in keywords:
        if len(out) >= limit:
            break
        url = BASE_LIST.format(kw=urllib.parse.quote_plus(kw))
        try:
            body = _fetch(url)
            logger.debug("PPH HTML GET %s", url)
        except Exception as e:
            logger.debug("PPH GET failed %s: %s", url, e)
            continue
        jobs = _parse_listing(body)
        # De-dup and cut per keyword
        seen = set(x.get("url") for x in out)
        for j in jobs:
            if j["url"] in seen:
                continue
            seen.add(j["url"])
            out.append(j)
            if sum(1 for x in out if kw.lower() in (x["title"] or "").lower()) >= PER_KEYWORD_LIMIT:
                break
        if len(out) >= limit:
            break
    # Unique by URL
    uniq = []
    seen = set()
    for j in out:
        u = j.get("url")
        if u and u not in seen:
            seen.add(u); uniq.append(j)
    return uniq[:limit]
