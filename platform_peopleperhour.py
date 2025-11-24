
# platform_peopleperhour.py - Hybrid scraper client
import platform_peopleperhour_proxy as proxy

def get_items(keywords):
    jobs = proxy.fetch_jobs()
    results=[]
    for job in jobs:
        title=job.get('title','')
        desc=job.get('description','')
        for kw in keywords:
            if kw.lower() in title.lower() or kw.lower() in desc.lower():
                j=job.copy()
                j['matched_keyword']=kw
                results.append(j)
                break
    return results
