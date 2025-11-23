
# platform_freelancer.py
import requests, logging
log=logging.getLogger("freelancer")

API="https://www.freelancer.com/api/projects/0.1/projects/active/"

def get_items(keywords):
    try:
        r=requests.get(API, timeout=20)
        j=r.json()
        out=[]
        for p in j.get("result",[]):
            title=p.get("title","")
            desc=p.get("description","")
            for kw in keywords:
                if kw.lower() in title.lower() or kw.lower() in desc.lower():
                    out.append({
                        "title":title,
                        "description":desc,
                        "budget_min":p.get("minbudget"),
                        "budget_max":p.get("maxbudget"),
                        "original_currency":p.get("currency",{}).get("code","USD"),
                        "url":f"https://www.freelancer.com/projects/{p.get('seo_url','')}",
                        "source":"Freelancer",
                        "matched_keyword":kw
                    })
                    break
        return out
    except Exception as e:
        log.warning(e)
        return []
