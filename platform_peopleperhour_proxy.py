
# platform_peopleperhour_proxy.py - Hybrid scraper
import httpx
from bs4 import BeautifulSoup

BASE="https://pph-proxy.onrender.com"

def fetch_jobs():
    # Try JSON endpoint
    try:
        r=httpx.get(f"{BASE}/jobs",timeout=20)
        if r.status_code==200:
            data=r.json()
            if isinstance(data,list):
                return data
    except:
        pass
    # fallback HTML
    try:
        r=httpx.get(f"{BASE}/jobs_html",timeout=20)
        soup=BeautifulSoup(r.text,"html.parser")
        jobs=[]
        for item in soup.select(".job-tile"):
            title=item.select_one(".job-title")
            desc=item.select_one(".job-description")
            jobs.append({
                "title": title.get_text(strip=True) if title else "",
                "description": desc.get_text(strip=True) if desc else "",
                "source": "PPH"
            })
        return jobs
    except:
        return []
