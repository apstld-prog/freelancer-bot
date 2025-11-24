# platform_skywalker.py — SKY PROXY VERSION (ATOM + RSS SUPPORT FIXED)
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

    # Try XML first
    try:
        soup = BeautifulSoup(raw, "xml")
    except Exception:
        soup = BeautifulSoup(raw, "html.parser")

    items = []

    # Detect if it's ATOM or RSS
    atom_entries = soup.find_all("entry")
    rss_items    = soup.find_all("item")

    # -------------------------------------------------------
    # ATOM FEED PARSING (Skywalker modern feed)
    # -------------------------------------------------------
    if atom_entries:
        for e in atom_entries:

            title = e.title.text.strip() if e.title else ""

            # FIX: BeautifulSoup get() only accepts (attr, default)
            if e.link:
                link = e.link.get("href", "").strip()
            else:
                link = ""

            desc = ""  # Atom feed does not include description
            pub  = e.publishDate.text.strip() if e.publishDate else ""

            try:
                ts = datetime.fromisoformat(pub.replace("Z", "+00:00"))
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

    # -------------------------------------------------------
    # RSS FALLBACK (older Skywalker feed)
    # -------------------------------------------------------
    for item in rss_items:
        title = item.title.text.strip() if item.title else ""
        desc  = item.description.text.strip() if item.description else ""
        link  = item.link.text.strip() if item.link else ""
        pub   = item.pubDate.text.strip() if item.pubDate else ""

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
        desc  = it.get("description", "")
        for kw in keywords:
            k = kw.lower()
            if k in title.lower() or k in desc.lower():
                x = it.copy()
                x["matched_keyword"] = kw
                out.append(x)
                break
    return out
