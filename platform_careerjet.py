# platform_careerjet.py
import requests
from xml.etree import ElementTree as ET
from html import unescape

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobBot/1.0)"}

def fetch(rss_url: str):
    """
    Î Î±Î¯ÏÎ½ÎµÎ¹ RSS Î±Ï€ÏŒ Careerjet (Ï€.Ï‡. Î•Î»Î»Î¬Î´Î±).
    Î Î±ÏÎ¬Î´ÎµÎ¹Î³Î¼Î± rss_url:
      - https://www.careerjet.gr/rss?s=&l=Î•Î»Î»Î¬Î´Î±
      - Î® Î¬Î»Î»Î¿ feed URL Ï„Î·Ï‚ Careerjet
    """
    out = []
    if not rss_url:
        return out
    resp = requests.get(rss_url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    tree = ET.fromstring(resp.content)
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
            "source": "Careerjet",
            "platform": "careerjet",
        })
    return out



