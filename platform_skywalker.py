# platform_skywalker.py
import requests
from xml.etree import ElementTree as ET
from html import unescape

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobBot/1.0)"}

def fetch(rss_url: str):
    """
    Παίρνει RSS όπως: https://www.skywalker.gr/jobs/feed
    Επιστρέφει list[dict] με πεδία: title, url, description, source, platform
    """
    out = []
    if not rss_url:
        return out
    resp = requests.get(rss_url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    tree = ET.fromstring(resp.content)
    # RSS 2.0: <item><title>..<link>..<description>..</item>
    for item in tree.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = unescape((item.findtext("description") or "").strip())
        if not title or not link:
            continue
        out.append({
            "title": title,
            "url": link,
            "description": desc,
            "source": "Skywalker",
            "platform": "skywalker",
        })
    return out
