# platform_skywalker.py — FINAL RENDER VERSION 2025 (WORKING)
import httpx
from bs4 import BeautifulSoup

from datetime import datetime

FEED_URL = "https://www.skywalker.gr/jobs/feed"


def fetch(feed_url=FEED_URL):
    """
    Fetch Skywalker RSS feed with safe HTML fallback.
    Skywalker sometimes returns HTML instead of XML, so BeautifulSoup("xml")
    will fail silently and return 0 items.
    """
    try:
        r = httpx.get(feed_url, timeout=20)
        r.raise_for_status()
    except Exception:
        return []

    raw = r.text.strip()

    # Try XML first — but if parsing fails, fallback to HTML
    soup = None
    try:
        soup = BeautifulSoup(raw, "xml")
        if not soup.find("item"):
            raise Exception("XML parser returned no items")
    except Exception:
        soup = BeautifulSoup(raw, "html.parser")

    items = []
    for item in soup.find_all("item"):
        try:
            title = item.title.text.strip() if item.title else ""
            desc = item.description.text.strip() if item.description else ""
            link = item.link.text.strip() if item.link else ""
            pub = item.pubDate.text.strip() if item.pubDate else ""

            try:
                ts = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %z")
            except Exception:
                ts = None

            items.append(
                {
                    "title": title,
                    "description": desc,
                    "link": link,
                    "pub_date": ts,
                    "source": "Skywalker",
                }
            )
        except:
            continue

    return items


def get_items(keywords):
    """
    Keyword-based filter for unified worker.
    """
    data = fetch()
    out = []
    for it in data:
        title = it.get("title", "")
        desc = it.get("description", "")
        for kw in keywords:
            lowkw = kw.lower()
            if lowkw in title.lower() or lowkw in desc.lower():
                x = it.copy()
                x["matched_keyword"] = kw
                out.append(x)
                break
    return out
