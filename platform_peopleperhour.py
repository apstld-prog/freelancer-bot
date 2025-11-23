
# platform_peopleperhour.py
import requests, logging
log=logging.getLogger("pph")

PROXY="https://pph-proxy.onrender.com/jobs"

def get_items(keywords):
    try:
        r=requests.get(PROXY, timeout=20)
        jobs=r.json()
        out=[]
        for j in jobs:
            title=j.get("title","")
            desc=j.get("description","")
            for kw in keywords:
                if kw.lower() in title.lower() or kw.lower() in desc.lower():
                    j2=j.copy()
                    j2["matched_keyword"]=kw
                    j2["source"]="PeoplePerHour"
                    out.append(j2)
                    break
        return out
    except Exception as e:
        log.warning(e)
        return []
