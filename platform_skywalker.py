
# platform_skywalker.py
import requests, logging
from bs4 import BeautifulSoup
log=logging.getLogger("sky")

RSS="https://www.skywalker.gr/jobs/feed"

def get_items(keywords):
    try:
        r=requests.get(RSS, timeout=20)
        soup=BeautifulSoup(r.text, "xml")
        items=soup.find_all("item")
        out=[]
        for it in items:
            title=it.title.text if it.title else ""
            desc=it.description.text if it.description else ""
            link=it.link.text if it.link else ""
            for kw in keywords:
                if kw.lower() in title.lower() or kw.lower() in desc.lower():
                    out.append({
                        "title":title,
                        "description":desc,
                        "url":link,
                        "source":"Skywalker",
                        "matched_keyword":kw
                    })
                    break
        return out
    except Exception as e:
        log.warning(e)
        return []
