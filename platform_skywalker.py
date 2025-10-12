import re
import html
import xml.etree.ElementTree as ET
import requests
from typing import List, Dict


SKYWALKER_FEED_URL = "https://www.skywalker.gr/rss/jobs"  # σταθερό RSS feed όλων των αγγελιών


def parse_rss(xml_text: str) -> List[Dict]:
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items

    channel = root.find("channel") or root
    for it in channel.findall("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        desc = html.unescape((it.findtext("description") or "").strip())
        clean_desc = re.sub("<[^<]+?>", "", desc)
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


def fetch(keywords: List[str] | str = None, timeout: int = 10) -> List[Dict]:
    """Fetch Skywalker RSS feed (ignores query, filters locally)."""
    try:
        resp = requests.get(SKYWALKER_FEED_URL, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        all_items = parse_rss(resp.text)

        # Filter τοπικά με keywords
        if keywords:
            if isinstance(keywords, str):
                kw_list = [keywords.lower()]
            else:
                kw_list = [k.lower() for k in keywords if k]
            filtered = []
            for item in all_items:
                text = (item.get("title", "") + " " + item.get("description", "")).lower()
                if any(k in text for k in kw_list):
                    filtered.append(item)
            return filtered
        else:
            return all_items

    except Exception as e:
        print("[skywalker] fetch error:", e)
        return []
