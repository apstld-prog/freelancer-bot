
# platform_peopleperhour.py — API-style scraper via embedded JSON
import re, json

HTML_PATH = "/opt/render/project/src/pph_cache.html"

def _load_json_from_html(html: str):
    start = html.find('{"activeTabs"')
    if start == -1:
        return []
    end = html.find("};", start)
    if end == -1:
        return []
    blob = html[start:end+1]
    try:
        data = json.loads(blob)
        # jobs likely under data["dashboard"]["jobs"]["openJobs"]
        jobs = data.get("dashboard",{}).get("jobs",{})
        out = []
        for listname in jobs:
            arr = jobs[listname]
            if isinstance(arr, list):
                out.extend(arr)
        return out
    except:
        return []

def fetch():
    try:
        with open(HTML_PATH, "r", encoding="utf-8", errors="ignore") as f:
            html = f.read()
    except:
        return []
    raw_jobs = _load_json_from_html(html)
    out=[]
    for j in raw_jobs:
        out.append({
            "title": j.get("title",""),
            "description": j.get("description",""),
            "budget_min": j.get("minBudget"),
            "budget_max": j.get("maxBudget"),
            "original_currency": j.get("currencyCode"),
            "link": "https://www.peopleperhour.com" + j.get("seoUrl",""),
            "source": "PeoplePerHour"
        })
    return out

def get_items(keywords):
    items = fetch()
    res=[]
    for it in items:
        t = (it.get("title","") + " " + it.get("description","")).lower()
        for kw in keywords:
            if kw.lower() in t:
                x = it.copy()
                x["matched_keyword"]=kw
                res.append(x)
                break
    return res
