
import re
import html
import xml.etree.ElementTree as ET
import requests
from typing import List, Dict

def parse_rss(xml_text: str) -> List[Dict]:
    items: List[Dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    channel = root.find('channel') or root
    for it in channel.findall('item'):
        title = (it.findtext('title') or '').strip()
        link = (it.findtext('link') or '').strip()
        desc = (it.findtext('description') or '').strip()
        desc = html.unescape(re.sub('<[^<]+?>', '', desc)).strip()
        if not title or not link:
            continue
        items.append({
            "title": title,
            "description": desc,
            "url": link,
            "budget_min": None,
            "budget_max": None,
            "currency": "EUR",
            "source": "kariera",
            "affiliate": False,
        })
    return items

def fetch(feed_url: str, timeout: int = 10) -> List[Dict]:
    # Kariera δεν προσφέρει δημόσιο RSS από default· χρησιμοποιούμε όποιο URL μας δώσεις μέσω env.
    if not feed_url:
        return []
    try:
        resp = requests.get(feed_url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        return parse_rss(resp.text)
    except Exception:
        return []
