
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from time import mktime
from email.utils import parsedate

RSS_URL = "https://www.peopleperhour.com/job-feed.xml"

def get_items(keywords):
    keywords = [k.lower() for k in (keywords or [])]
    out = []
    try:
        r = requests.get(RSS_URL, timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.text)

        for item in root.findall("./channel/item"):
            title = (item.findtext("title") or "").strip()
            desc = (item.findtext("description") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = item.findtext("pubDate")
            ts = int(mktime(parsedate(pub))) if pub else None

            matched = None
            hay = f"{title.lower()}\n{desc.lower()}"
            for kw in keywords:
                if kw in hay:
                    matched = kw
                    break
            if keywords and not matched:
                continue

            out.append({
                "source": "peopleperhour",
                "title": title,
                "description": desc,
                "url": link,
                "proposal_url": link,
                "budget_min": None,
                "budget_max": None,
                "original_currency": None,
                "matched_keyword": matched,
                "time_submitted": ts,
                "affiliate": False
            })
    except Exception:
        pass
    return out
