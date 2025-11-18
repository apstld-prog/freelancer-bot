# platform_peopleperhour.py
import feedparser, re

RSS_FEEDS = [
    "https://www.peopleperhour.com/freelance-jobs.rss",
    "https://www.peopleperhour.com/freelance-jobs/design.rss",
    "https://www.peopleperhour.com/freelance-jobs/development.rss",
]

def _clean(s):
    return (s or "").strip()

def _extract_budget(text):
    if not text:
        return None, None, None
    txt = text.replace(",", "")
    cur = "GBP" if "£" in txt else "EUR" if "€" in txt else "USD" if "$" in txt else None
    nums = re.findall(r"\d+(?:\.\d+)?", txt)
    if not nums:
        return None, None, cur
    vals = list(map(float, nums))
    return vals[0], vals[-1], cur

def convert_to_usd(v, c):
    if not v or not c:
        return None
    rates = {"USD": 1, "EUR": 1.08, "GBP": 1.27}
    return round(v * rates.get(c.upper(), 1), 2)

def get_items(keywords):
    out = []
    for url in RSS_FEEDS:
        parsed = feedparser.parse(url)
        entries = parsed.entries[:100]
        for e in entries:
            title = _clean(e.get("title", ""))
            desc = _clean(e.get("summary", ""))
            link = e.get("link", "")
            txt = f"{title} {desc}".lower()
            for kw in keywords:
                if kw.lower() in txt:
                    bmin, bmax, cur = _extract_budget(title)
                    out.append({
                        "source": "peopleperhour",
                        "matched_keyword": kw,
                        "title": title,
                        "description": desc,
                        "original_url": link,
                        "budget_min": bmin,
                        "budget_max": bmax,
                        "original_currency": cur,
                        "usd_min": convert_to_usd(bmin, cur),
                        "usd_max": convert_to_usd(bmax, cur),
                    })
    return out
