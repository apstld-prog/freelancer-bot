
import re
import html
import xml.etree.ElementTree as ET
import requests
from typing import List, Dict

def parse_rss(xml_text: str) -> List[Dict]:
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    channel = root.find('channel') or root
    for it in channel.findall('item'):
        title = (it.findtext('title') or '').strip()
        link = (it.findtext('link') or '').strip()
        desc = html.unescape((it.findtext('description') or '').strip())
        clean_desc = re.sub('<[^<]+?>', '', desc)
        item = {
            "external_id": link or title,
            "title": title,
            "description": clean_desc,
            "url": link,
            "budget_min": None,
            "budget_max": None,
            "currency": "EUR",
            "source": "skywalker",
            "affiliate": False,
        }
        items.append(item)
    return items

def fetch(feed_url: str, timeout: int = 10) -> List[Dict]:
    try:
        resp = requests.get(feed_url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        return parse_rss(resp.text)
    except Exception:
        return []
