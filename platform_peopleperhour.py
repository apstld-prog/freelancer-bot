import httpx
import json
import re

def _clean(s):
    return (s or "").strip()

def _extract_budget(amount):
    if not amount:
        return None, None, None
    txt = str(amount)
    if "£" in txt:
        cur="GBP"
    elif "€" in txt:
        cur="EUR"
    elif "$" in txt:
        cur="USD"
    else:
        cur=None
    nums = re.findall(r"\d+(?:\.\d+)?", txt)
    if not nums:
        return None,None,cur
    nums=list(map(float,nums))
    if len(nums)==1:
        return nums[0],nums[0],cur
    return nums[0],nums[-1],cur

def get_items(keywords):
    out=[]
    for kw in keywords:
        url=f"https://www.peopleperhour.com/freelance-jobs?q={kw}"
        r=httpx.get(url,headers={"User-Agent":"Mozilla/5.0"})
        text=r.text
        import re
        m=re.search(r"<script id=\"__NEXT_DATA__\" type=\"application/json\">(.*?)</script>",text,re.S)
        if not m:
            continue
        data=json.loads(m.group(1))
        projects=data.get("props",{}).get("pageProps",{}).get("projects",[])
        for pr in projects:
            title=_clean(pr.get("title"))
            desc=_clean(pr.get("description"," "))
            hay=f"{title} {desc}".lower()
            if kw.lower() not in hay:
                continue
            amount=pr.get("budget",{})
            btxt= amount.get("amount") or amount.get("minimumAmount") or amount.get("maximumAmount")
            bmin,bmax,cur=_extract_budget(str(btxt))
            out.append({
                "source":"peopleperhour",
                "matched_keyword":kw,
                "title":title,
                "description":desc,
                "original_url":"https://www.peopleperhour.com"+pr.get("path"," "),
                "budget_min":bmin,
                "budget_max":bmax,
                "original_currency":cur
            })
    return out
