
from __future__ import annotations

import os, re, html, email.utils as eut
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any

import httpx

try:
    from bs4 import BeautifulSoup  # type: ignore
except Exception:
    BeautifulSoup = None

PPH_HOST = "https://www.peopleperhour.com"


def _log(msg: str, **kv):
    blob = " ".join([f"{k}={v}" for k, v in kv.items()]) if kv else ""
    print(f"PPH debug: {msg} {blob}".strip(), flush=True)


def _env_bool(name: str, default: bool=False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


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
    if m:
        return m.group(1)
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
            if not link:
                continue
            if not dt:
                dt = datetime.now(timezone.utc)
            items.append(_norm_item(_extract_id_from_link(link), title, desc, link, dt))
    except Exception as e:
        _log("RSS fetch error", url=url, err=repr(e))
    return items


def _fetch_html_search(keyword: str, timeout: float=15.0):
    if BeautifulSoup is None:
        _log("bs4 not available — skip HTML fallback")
        return []
    url = f"{PPH_HOST}/freelance-jobs?search={keyword}"
    items = []
    try:
        with httpx.Client(timeout=timeout, headers={"User-Agent": "Mozilla/5.0"}) as client:
            resp = client.get(url)
            _log("HTML GET", url=url, status=resp.status_code)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

        for a in soup.select('a[href*="/freelance-jobs/"], a[href*="/job/"]'):
            href = a.get("href") or ""
            if not href:
                continue
            # skip pure category links lacking numeric id
            if "/freelance-jobs/" in href and re.search(r"-\d{5,}", href) is None:
                continue
            link = href if href.startswith("http") else (PPH_HOST + href)
            title = (a.get_text(" ", strip=True) or "").strip() or (a.get("title") or "").strip()
            parent = a.find_parent()
            desc = ""
            if parent:
                p = parent.find("p")
                if p:
                    desc = p.get_text(" ", strip=True)
            dt = datetime.now(timezone.utc)
            items.append(_norm_item(_extract_id_from_link(link), title, desc, link, dt))

        seen, out = set(), []
        for it in items:
            if it["id"] in seen:
                continue
            seen.add(it["id"])
            out.append(it)
        return out
    except Exception as e:
        _log("HTML fetch error", url=url, err=repr(e))
        return []


def get_items(*_args, **_kwargs):
    # Accept any positional/keyword args to be compatible with worker signature.
    if not (_env_bool("ENABLE_PPH", True) or _env_bool("P_PEOPLEPERHOUR", False)):
        _log("PPH disabled via env")
        return []

    fresh_hours = int(os.getenv("FRESH_WINDOW_HOURS", "48"))
    dynamic_from_keywords = _env_bool("PPH_DYNAMIC_FROM_KEYWORDS", True)
    keywords = _keywords_from_env() if dynamic_from_keywords else []

    urls = _rss_urls_from_env(keywords) if (dynamic_from_keywords or not os.getenv("PPH_RSS_URLS")) else [u.strip() for u in os.getenv("PPH_RSS_URLS","").split(",") if u.strip()]

    _log("start", fresh_hours=fresh_hours, kwords=",".join(keywords), urls=len(urls))

    all_items = []
    for url in urls:
        all_items.extend(_fetch_rss(url))

    if not all_items and keywords:
        _log("fallback: html search")
        for kw in keywords:
            all_items.extend(_fetch_html_search(kw))

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
