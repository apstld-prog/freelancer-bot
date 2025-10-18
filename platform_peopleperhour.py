# platform_peopleperhour.py — RSS-based PeoplePerHour fetcher (48h freshness)
from typing import List, Dict, Optional
import os, re, html
from datetime import datetime, timezone, timedelta
import httpx
import xml.etree.ElementTree as ET

FRESH_HOURS = int(os.getenv("FRESH_WINDOW_HOURS", "48"))
USER_AGENT = os.getenv("HTTP_USER_AGENT", "Mozilla/5.0 (compatible; JobBot/1.0)")

def _parse_rss_datetime(s: str) -> Optional[datetime]:
    if not s: return None
    s = s.strip()
    fmts = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(s.replace("GMT","+0000"), fmt)
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
            else: dt = dt.astimezone(timezone.utc)
            return dt
        except Exception:
            pass
    return None

def _strip_html(s: str) -> str:
    try:
        text = re.sub(r"<[^>]+>", " ", s or "", flags=re.S|re.I)
        return html.unescape(resub(r"\s+", " ", text)).strip()
    except Exception:
        return (s or "").strip()

def _match_keyword(title: str, description: str, keywords: List[str]) -> Optional[str]:
    hay = f"{(title or '').lower()}\n{(description or '').lower()}"
    for kw in keywords or []:
        k = (kw or "").strip().lower()
        if k and k in hay: return kw
    return None

def _fetch_rss(url: str, timeout: float = 15.0) -> List[Dict]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8"}
    r = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    items: List[Dict] = []
    try:
        root = ET.fromstring(r.text)
    except Exception:
        return items
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        desc = _strip_html(item.findtext("description") or "")
        items.append({"title": title,"description": desc,"url": link,"original_url": link,"source": "peopleperhour","date": pub})
    if not items:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//a:entry", ns):
            title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
            link_el = entry.find("a:link", ns)
            link = (link_el.attrib.get("href") if link_el is not None else "").strip()
            pub = (entry.findtext("a:updated", default="", namespaces=ns) or "").strip()
            desc = _strip_html(entry.findtext("a:summary", default="", namespaces=ns) or "")
            items.append({"title": title,"description": desc,"url": link,"original_url": link,"source": "peopleperhour","date": pub})
    return items

def get_items(keywords: List[str]) -> List[Dict]:
    if not (os.getenv("ENABLE_PPH","0")=="1" and os.getenv("P_PEOPLEPERHOUR","0")=="1"):
        return []
    urls_env = os.getenv("PPH_RSS_URLS","").strip()
    if not urls_env: return []
    urls = [u.strip() for u in urls_env.split(",") if u.strip()]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=FRESH_HOURS)
    out: List[Dict] = []
    for url in urls:
        try:
            items = _fetch_rss(url)
        except Exception:
            items = []
        for it in items:
            dt = _parse_rss_datetime(it.get("date") or "")
            if not dt or dt < cutoff: continue
            mk = _match_keyword(it.get("title",""), it.get("description",""), keywords or [])
            if mk: it["matched_keyword"] = mk
            out.append(it)
    seen=set(); uniq=[]
    for it in out:
        key = (it.get("url") or it.get("original_url") or "").strip() or f"pph::{(it.get('title') or '')[:160]}"
        if key in seen: continue
        seen.add(key); uniq.append(it)
    return uniq
