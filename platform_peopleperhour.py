
from __future__ import annotations
import os, re, html, email.utils as eut
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
import httpx

PPH_HOST = "https://www.peopleperhour.com"

def _log(msg: str, **kv):
    blob = " ".join([f"{k}={v}" for k,v in kv.items()]) if kv else ""
    print(f"PPH debug: {msg} {blob}".strip(), flush=True)

def _env_bool(name: str, default: bool=False) -> bool:
    v = os.getenv(name)
    if v is None: return default
    return v.strip().lower() in ("1","true","yes","on")

def _parse_pubdate(pub: str):
    try:
        dt = eut.parsedate_to_datetime(pub)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None

def _within_window(dt: datetime, fresh_hours: int) -> bool:
    now = datetime.now(timezone.utc)
    return (now - dt) <= timedelta(hours=fresh_hours)

def _keywords_from_env() -> List[str]:
    raw = os.getenv("KEYWORDS") or os.getenv("KEYWORDS_CSV") or ""
    parts = re.split(r"[,\s]+", raw.strip())
    return [p for p in parts if p]

def _rss_urls_from_env(keywords: List[str]) -> List[str]:
    tpl = os.getenv("PPH_RSS_URLS", "").strip()
    urls: List[str] = []
    if tpl:
        if "{keywords}" in tpl:
            kwq = ",".join(keywords) if keywords else ""
            urls.append(tpl.replace("{keywords}", kwq))
        else:
            urls.extend([u.strip() for u in tpl.split(",") if u.strip()])
    else:
        for kw in keywords:
            urls.append(f"{PPH_HOST}/freelance-jobs?rss=1&search={kw}")
    return urls

def _norm_item(source_id: str, title: str, description: str, link: str, posted: datetime) -> Dict[str, Any]:
    return {
        "id": f"pph:{source_id}",
        "title": title.strip() if title else "(no title)",
        "description": description.strip() if description else "",
        "link": link,
        "source": "peopleperhour",
        "budget": None,
        "currency": None,
        "posted_at": posted.astimezone(timezone.utc).isoformat()
    }

def _extract_id_from_link(link: str) -> str:
    m = re.search(r"-([0-9]{5,})/?$", link)
    if m: return m.group(1)
    import hashlib
    return hashlib.md5(link.encode("utf-8")).hexdigest()[:12]

def _fetch_rss(url: str, timeout: float=15.0):
    items = []
    try:
        with httpx.Client(timeout=timeout, headers={"User-Agent": "Mozilla/5.0"}) as client:
            resp = client.get(url)
            _log("RSS GET", url=url, status=resp.status_code)
            resp.raise_for_status()
            txt = resp.text
        entries = re.findall(r"<item>(.*?)</item>", txt, flags=re.S | re.I)
        for raw in entries:
            title = html.unescape(re.search(r"<title>(.*?)</title>", raw, flags=re.S|re.I).group(1)) if re.search(r"<title>(.*?)</title>", raw, flags=re.S|re.I) else ""
            link = html.unescape(re.search(r"<link>(.*?)</link>", raw, flags=re.S|re.I).group(1)) if re.search(r"<link>(.*?)</link>", raw, flags=re.S|re.I) else ""
            desc = html.unescape(re.search(r"<description>(.*?)</description>", raw, flags=re.S|re.I).group(1)) if re.search(r"<description>(.*?)</description>", raw, flags=re.S|re.I) else ""
            pub = re.search(r"<pubDate>(.*?)</pubDate>", raw, flags=re.S|re.I)
            dt = _parse_pubdate(pub.group(1)) if pub else None
            if not link: continue
            if not dt: dt = datetime.now(timezone.utc)
            items.append(_norm_item(_extract_id_from_link(link), title, desc, link, dt))
    except Exception as e:
        _log("RSS fetch error", url=url, err=repr(e))
    return items

# BeautifulSoup-free HTML parser (regex-based) for search results and job pages
_JOB_LINK_RE = re.compile(r'href="(?P<h>/freelance-jobs/[^"#?]*?-\d{5,})"', re.I)
_TITLE_RE = re.compile(r'<h1[^>]*>(?P<t>.*?)</h1>', re.I|re.S)
_BUDGET_RE = re.compile(r'(?:(?:Budget|Fixed Price|Hourly Rate)\s*[:\-]?\s*)(?P<amt>[\$€£]?\s?\d[\d,\.]*)', re.I)
_CURRENCY_RE = re.compile(r'[\$€£]|USD|EUR|GBP', re.I)

def _clean_html(text: str) -> str:
    # strip tags quickly
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return text

def _fetch_job_page(link: str, timeout: float=15.0):
    """Fetch individual job page to get title/description/budget when search cards are bare."""
    try:
        with httpx.Client(timeout=timeout, headers={"User-Agent": "Mozilla/5.0"}) as client:
            resp = client.get(link)
            _log("JOB GET", url=link, status=resp.status_code)
            resp.raise_for_status()
            htmltxt = resp.text
        title = ""
        m = _TITLE_RE.search(htmltxt)
        if m:
            title = _clean_html(m.group("t"))
        # crude description grab: take meta description or first paragraph-like chunk
        desc = ""
        mmeta = re.search(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']', htmltxt, flags=re.I|re.S)
        if mmeta:
            desc = _clean_html(mmeta.group(1))
        if not desc:
            mp = re.search(r"<p[^>]*>(.*?)</p>", htmltxt, flags=re.I|re.S)
            if mp:
                desc = _clean_html(mp.group(1))
        budget = None
        currency = None
        mb = _BUDGET_RE.search(htmltxt)
        if mb:
            raw = _clean_html(mb.group("amt"))
            # split symbol from number
            curm = _CURRENCY_RE.search(raw or "")
            if curm:
                sym = curm.group(0).upper()
                currency = {"$":"USD","USD":"USD","€":"EUR","EUR":"EUR","£":"GBP","GBP":"GBP"}.get(sym, sym)
            num = re.sub(r"[^\d\.]", "", raw)
            try:
                budget = float(num) if num else None
            except Exception:
                budget = None
        return title, desc, budget, currency
    except Exception as e:
        _log("JOB fetch error", url=link, err=repr(e))
        return "", "", None, None

def _html_search_regex(keyword: str, timeout: float=15.0):
    url = f"{PPH_HOST}/freelance-jobs?search={keyword}"
    try:
        with httpx.Client(timeout=timeout, headers={"User-Agent": "Mozilla/5.0"}) as client:
            resp = client.get(url)
            _log("HTML GET", url=url, status=resp.status_code)
            resp.raise_for_status()
            htmltxt = resp.text
        links = []
        for m in _JOB_LINK_RE.finditer(htmltxt):
            href = m.group("h")
            if href and re.search(r"-\d{5,}", href):
                link = href if href.startswith("http") else (PPH_HOST + href)
                links.append(link)
        # de-dup
        links = list(dict.fromkeys(links))
        items = []
        for link in links:
            jid = _extract_id_from_link(link)
            title, desc, budget, currency = _fetch_job_page(link)
            if not title:
                # fallback: derive minimal title from slug
                title = html.unescape(link.split("/")[-1].replace("-", " ").split(jid)[0]).strip().title()
            dt = datetime.now(timezone.utc)
            it = _norm_item(jid, title, desc, link, dt)
            it["budget"], it["currency"] = budget, currency
            items.append(it)
        return items
    except Exception as e:
        _log("HTML fetch error", url=url, err=repr(e))
        return []

def get_items(*_args, **_kwargs):
    if not (_env_bool("ENABLE_PPH", True) or _env_bool("P_PEOPLEPERHOUR", False)):
        _log("PPH disabled via env")
        return []
    fresh_hours = int(os.getenv("FRESH_WINDOW_HOURS", "48"))
    dynamic_from_keywords = _env_bool("PPH_DYNAMIC_FROM_KEYWORDS", True)
    keywords = _keywords_from_env() if dynamic_from_keywords else []

    urls = _rss_urls_from_env(keywords) if (dynamic_from_keywords or not os.getenv("PPH_RSS_URLS")) else [u.strip() for u in os.getenv("PPH_RSS_URLS","").split(",") if u.strip()]
    _log("start", fresh_hours=fresh_hours, kwords=",".join(keywords), urls=len(urls))

    all_items = []
    # 1) RSS
    for url in urls:
        all_items.extend(_fetch_rss(url))

    # 2) HTML regex fallback (works without bs4)
    if not all_items and keywords:
        _log("fallback: html regex")
        for kw in keywords:
            all_items.extend(_html_search_regex(kw))

    # filter window + keyword match
    filtered = []
    for it in all_items:
        try:
            dt = datetime.fromisoformat(it["posted_at"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            dt = datetime.now(timezone.utc)
        if not _within_window(dt, fresh_hours):
            continue
        if keywords:
            text = f"{it.get('title','')} {it.get('description','')}".lower()
            if not any(kw.lower() in text for kw in keywords):
                continue
        filtered.append(it)

    _log("done", fetched=len(all_items), fresh=len(filtered))
    return filtered
