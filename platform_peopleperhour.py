
import requests, time
from bs4 import BeautifulSoup

def get_items(keywords):
    url="https://www.peopleperhour.com/freelance-jobs"
    try:
        r=requests.get(url,headers={"User-Agent":"Mozilla/5.0"})
        html=r.text
    except:
        return []
    soup=BeautifulSoup(html,"html.parser")
    items=[]
    for li in soup.find_all("li",class_=lambda x: x and "list__item" in x):
        a=li.find("a",href=True)
        if not a: continue
        title=a.get_text(strip=True)
        href=a['href']
        desc=""
        price=None
        for span in li.find_all("span"):
            t=span.get_text(strip=True)
            if any(c in t for c in ["$","€","£"]):
                price=t
                break
        item={"title":title,"url":href,"description":desc,"matched_keyword":None,"source":"peopleperhour"}
        if price:
            clean=price.replace("$","").replace("€","").replace("£","")
            item["budget_min"]=item["budget_max"]=clean
        if keywords:
            hay=title.lower()
            mk=None
            for kw in keywords:
                if kw.lower() in hay:
                    mk=kw
                    break
            if not mk: continue
            item["matched_keyword"]=mk
        items.append(item)
    return items
