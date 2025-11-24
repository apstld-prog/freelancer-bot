# platform_skywalker.py — SKY PROXY VERSION
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

PROXY_URL = "https://freelancer-bot-ns7s.onrender.com/skywalker_proxy"


def fetch():
    try:
        r = httpx.get(PROXY_URL, timeout=20)
        r.raise_for_status()
    except Exception:
        return []

    raw = r.text.strip()

    # Try XML, fallback HTML
    try:
        soup = BeautifulSoup(raw, "xml")
        if not soup.find("item"):
            raise Exception("xml empty")
    except Exception:
        soup = BeautifulSoup(raw, "html.parser")

    items = []
    for item in soup.find_all("item"):
        title = item.title.text.strip() if item.title else ""
        desc = item.description.text.strip() if item.description else ""
        link = item.link.text.strip() if item.link else ""
        pub = item.pubDate.text.strip() if item.pubDate else ""

        try:
            ts = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %z")
        except:
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
    out = []
    for it in data:
        title = it.get("title", "")
        desc = it.get("description", "")
        for kw in keywords:
            k = kw.lower()
            if k in title.lower() or k in desc.lower():
                x = it.copy()
                x["matched_keyword"] = kw
                out.append(x)
                break
    return out
