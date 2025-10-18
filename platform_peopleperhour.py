
# platform_peopleperhour.py — dynamic RSS from user keywords with HTML fallback
from typing import List, Dict, Optional
import os, re, html, urllib.parse, logging
from datetime import datetime, timezone, timedelta
import httpx

log = logging.getLogger("pph")

FRESH_HOURS = int(os.getenv("FRESH_WINDOW_HOURS", "48"))
USER_AGENT = os.getenv("HTTP_USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 JobBot/1.0")
PPH_SEND_ALL = os.getenv("PPH_SEND_ALL", "0") == "1"
PPH_DYNAMIC_FROM_KEYWORDS = os.getenv("PPH_DYNAMIC_FROM_KEYWORDS", "0") == "1"
PPH_BASE = os.getenv("PPH_BASE_URL", "https://www.peopleperhour.com/freelance-jobs?search={kw}")

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
        return html.unescape(re.sub(r"\s+", " ", text)).strip()
    except Exception:
        return (s or "").strip()

def _match_keyword(title: str, description: str, keywords: List[str]) -> Optional[str]:
    hay = f"{(title or '').lower()}\n{(description or '').lower()}"
    for kw in keywords or []:
        k = (kw or "").strip().lower()
        if k and k in hay: return kw
    return None

def _terms_from_url(url: str) -> List[str]:
    try:
        q = urllib.parse.urlparse(url).query
        params = urllib.parse.parse_qs(q)
        raw = ",".join(params.get("search", [])).strip()
        if not raw: return []
        parts = re.split(r"[,+\s]+", urllib.parse.unquote_plus(raw))
        return [p.strip() for p in parts if p.strip()]
    except Exception:
        return []

def _build_urls(keywords: List[str]) -> List[str]:
    urls_env = (os.getenv("PPH_RSS_URLS","") or "").strip()
    if "{keywords}" in urls_env:
        joined = ",".join([urllib.parse.quote_plus(k.strip()) for k in keywords if k.strip()])
        return [urls_env.replace("{keywords}", joined)] if joined else []
    if PPH_DYNAMIC_FROM_KEYWORDS or not urls_env:
        urls = []
        for kw in keywords or []:
            k = kw.strip()
            if not k: continue
            urls.append(PPH_BASE.replace("{kw}", urllib.parse.quote_plus(k)))
        return urls
    return [u.strip() for u in urls_env.split(",") if u.strip()]

def _fetch(url: str, timeout: float = 15.0):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/rss+xml, application/xml;q=0.9, text/html;q=0.8, */*;q=0.7",
        "Referer": "https://www.peopleperhour.com/",
    }
    r = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    ctype = r.headers.get("Content-Type","").lower()
    return r.text, ctype

def _parse_rss(xml_text: str) -> List[Dict]:
    import xml.etree.ElementTree as ET
    items: List[Dict] = []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return items
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        desc = _strip_html(item.findtext("description") or "")
        items.append({
            "title": title,
            "description": desc,
            "url": link,
            "original_url": link,
            "source": "peopleperhour",
            "date": pub,
        })
    if not items:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//a:entry", ns):
            title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
            link_el = entry.find("a:link", ns)
            link = (link_el.attrib.get("href") if link_el is not None else "").strip()
            pub = (entry.findtext("a:updated", default="", namespaces=ns) or "").strip()
            desc = _strip_html(entry.findtext("a:summary", default="", namespaces=ns) or "")
            items.append({
                "title": title,
                "description": desc,
                "url": link,
                "original_url": link,
                "source": "peopleperhour",
                "date": pub,
            })
    return items

def _parse_html_list(html_text: str) -> List[Dict]:
    items: List[Dict] = []
    txt = re.sub(r"\s+", " ", html_text)
    pattern = re.compile(r'<a[^>]+href="(?P<href>/(?:freelance-jobs|job)/[^" ]+)"[^>]*>(?P<title>[^<]{5,120})</a>', re.I)
    seen = set()
    for m in pattern.finditer(txt):
        href = m.group("href")
        title = _strip_html(m.group("title"))
        if not title or not href: continue
        if href in seen: continue
        seen.add(href)
        full = "https://www.peopleperhour.com" + href
        items.append({
            "title": title,
            "description": "",
            "url": full,
            "original_url": full,
            "source": "peopleperhour",
            "date": datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z"),
        })
        if len(items) >= 50:
            break
    return items

def get_items(keywords: List[str]) -> List[Dict]:
    if not (os.getenv("ENABLE_PPH","0")=="1" and os.getenv("P_PEOPLEPERHOUR","0")=="1"):
        return []
    urls = _build_urls(keywords or [])
    if not urls: return []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=FRESH_HOURS)
    out: List[Dict] = []
    total_fetched = total_fresh = 0
    for url in urls:
        try:
            body, ctype = _fetch(url)
        except Exception as e:
            log.warning("PPH fetch failed: %s", e)
            continue
        items: List[Dict] = []
        if "xml" in ctype:
            items = _parse_rss(body)
        else:
            items = _parse_rss(body)  # try XML first in case mislabelled
            if not items:
                items = _parse_html_list(body)

        total_fetched += len(items)
        url_terms = _terms_from_url(url)
        for it in items:
            dt = _parse_rss_datetime(it.get("date") or "") or datetime.now(timezone.utc)
            if dt < cutoff:
                continue
            total_fresh += 1
            mk = _match_keyword(it.get("title",""), it.get("description",""), keywords or [])
            if not mk and url_terms and keywords:
                low_kws = { (k or '').strip().lower(): k for k in keywords }
                for t in url_terms:
                    lk = t.lower()
                    if lk in low_kws:
                        mk = low_kws[lk]
                        break
            if mk:
                it["matched_keyword"] = mk
                out.append(it)
            else:
                if PPH_SEND_ALL:
                    if url_terms:
                        it["matched_keyword"] = url_terms[0]
                    out.append(it)
    log.debug("PPH stats: fetched=%s fresh=%s sent=%s", total_fetched, total_fresh, len(out))
    seen=set(); uniq=[]
    for it in out:
        key = (it.get("url") or it.get("original_url") or "").strip() or f"pph::{(it.get('title') or '')[:160]}"
        if key in seen: continue
        seen.add(key); uniq.append(it)
    return uniq
