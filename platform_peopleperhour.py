
import re
import html
import requests
from typing import List, Dict, Optional
from urllib.parse import quote_plus

def _parse_html(html_text: str) -> List[Dict]:
    items: List[Dict] = []
    pattern = re.compile(r'<a[^>]+href="(?P<h>/[^"]*(?:/job/|/freelance-jobs/)[^"]+)"[^>]*>(?P<t>.*?)</a>', re.IGNORECASE)
    for m in pattern.finditer(html_text):
        href = m.group('h')
        title_raw = m.group('t')
        title = re.sub('<[^<]+?>', '', title_raw or '').strip()
        if not title:
            continue
        url = href
        if url.startswith('/'):
            url = 'https://www.peopleperhour.com' + url
        if any(i.get('url') == url for i in items):
            continue
        items.append({
            "title": html.unescape(title),
            "description": "",
            "url": url,
            "budget_min": None,
            "budget_max": None,
            "currency": "EUR",
            "source": "peopleperhour",
            "affiliate": False,
        })
    return items

def fetch(query: Optional[str] = None, timeout: int = 10) -> List[Dict]:
    base = "https://www.peopleperhour.com/freelance-jobs"
    url = base
    if query:
        url = f"{base}?q={quote_plus(query)}"
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        return _parse_html(resp.text)
    except Exception:
        return []
