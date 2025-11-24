
# platform_skywalker.py — FINAL STABLE VERSION (2025)
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

FEED_URL = "https://www.skywalker.gr/jobs/feed"

def fetch(feed_url=FEED_URL):
    try:
        r = httpx.get(feed_url, timeout=20)
        r.raise_for_status()
    except Exception:
        return []
    try:
        soup = BeautifulSoup(r.text, "xml")
    except Exception:
        soup = BeautifulSoup(r.text, "html.parser")

    items=[]
    for item in soup.find_all("item"):
        title = item.title.text if item.title else ""
        desc = item.description.text if item.description else ""
        link = item.link.text if item.link else ""
        pub = item.pubDate.text if item.pubDate else ""
        try:
            ts = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %z")
        except Exception:
            ts = None
        items.append({
            "title": title,
            "description": desc,
            "link": link,
            "pub_date": ts,
            "source": "Skywalker"
        })
    return items

def get_items(keywords):
    data = fetch()
    out=[]
    for it in data:
        title = it.get("title","")
        desc  = it.get("description","")
        for kw in keywords:
            k = kw.lower()
            if k in title.lower() or k in desc.lower():
                x = it.copy()
                x["matched_keyword"] = kw
                out.append(x)
                break
    return out
