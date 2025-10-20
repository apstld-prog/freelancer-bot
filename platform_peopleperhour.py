import os
import time
import datetime
import math
import random
import httpx
from bs4 import BeautifulSoup

FX_RATES = {"USD": 1.0, "EUR": 1.08, "GBP": 1.26}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}


def convert_to_usd(amount, currency):
    """Convert given amount to USD based on FX_RATES."""
    if not amount or not currency:
        return amount
    currency = currency.upper()
    rate = FX_RATES.get(currency, 1.0)
    return round(amount / rate, 2)


def budget_display(amount_min, amount_max, currency):
    """Return display string like £250 (~$315 USD / €290 EUR)."""
    if not currency:
        return f"${amount_min}-{amount_max}"
    ccy = currency.upper()
    sym = "£" if ccy == "GBP" else ("€" if ccy == "EUR" else ("$" if ccy == "USD" else ccy))
    if amount_min and amount_max:
        base = f"{sym}{amount_min}–{amount_max}"
    elif amount_min:
        base = f"{sym}{amount_min}+"
    else:
        base = f"{sym}{amount_max}"
    # USD/EUR conversion display
    try:
        usd_min = convert_to_usd(amount_min, ccy)
        usd_max = convert_to_usd(amount_max, ccy)
        eur_min = round(usd_min * FX_RATES["EUR"], 2) if usd_min else None
        eur_max = round(usd_max * FX_RATES["EUR"], 2) if usd_max else None
        if usd_min and usd_max:
            conv = f" (~${usd_min}-{usd_max} USD / €{eur_min}-{eur_max} EUR)"
        elif usd_min:
            conv = f" (~${usd_min} USD / €{eur_min} EUR)"
        else:
            conv = ""
        return base + conv
    except Exception:
        return base


def fetch_jobs(keywords, pages=5, delay=1.2):
    """Fetch jobs from PPH search pages."""
    results = []
    for kw in keywords:
        for p in range(1, pages + 1):
            url = f"https://www.peopleperhour.com/freelance-jobs?q={kw}&page={p}"
            try:
                r = httpx.get(url, headers=HEADERS, timeout=20.0)
                if r.status_code != 200:
                    time.sleep(delay)
                    continue
                soup = BeautifulSoup(r.text, "html.parser")
                cards = soup.find_all("a", href=True)
                job_links = [a["href"] for a in cards if "/freelance-jobs/" in a["href"]]
                for link in job_links:
                    if not link.startswith("http"):
                        link = "https://www.peopleperhour.com" + link
                    results.append({"keyword": kw, "url": link})
                time.sleep(delay)
            except Exception:
                continue
    return results


def parse_job_page(url):
    """Extract job info from job page."""
    try:
        r = httpx.get(url, headers=HEADERS, timeout=20.0)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.find("h1")
        desc = soup.find("div", {"class": "job-description"})
        budget_el = soup.find(string=lambda t: "Budget" in t)
        currency = "GBP"
        amount_min, amount_max = None, None
        if budget_el:
            try:
                text = budget_el.parent.get_text(strip=True)
                if "£" in text:
                    currency = "GBP"
                elif "$" in text:
                    currency = "USD"
                elif "€" in text:
                    currency = "EUR"
                nums = [float(x.replace(",", "")) for x in text.replace("–", "-").replace("to", "-").split("-") if x.strip().replace(".", "").isdigit()]
                if len(nums) == 1:
                    amount_min = nums[0]
                elif len(nums) >= 2:
                    amount_min, amount_max = nums[:2]
            except Exception:
                pass
        budget_str = budget_display(amount_min, amount_max, currency)
        return {
            "title": title.get_text(strip=True) if title else "",
            "description": desc.get_text(strip=True) if desc else "",
            "budget_display": budget_str,
            "url": url,
        }
    except Exception:
        return None


def keyword_match(job, keywords):
    """Return True if any keyword appears in title or description."""
    haystack = (job.get("title", "") + " " + job.get("description", "")).lower()
    for kw in keywords:
        if kw.lower() in haystack:
            job["matched_keyword"] = kw
            return True
    return False


def collect_pph_jobs(keywords):
    """Main collector."""
    found = []
    jobs = fetch_jobs(keywords)
    for j in jobs:
        job_data = parse_job_page(j["url"])
        if not job_data:
            continue
        if keyword_match(job_data, keywords):
            found.append(job_data)
    return found


# ✅ Compatibility wrapper for Render worker_runner
def get_items():
    keywords = ["logo", "lighting", "luminaire"]
    return collect_pph_jobs(keywords)


if __name__ == "__main__":
    keywords = ["logo", "lighting", "luminaire"]
    data = collect_pph_jobs(keywords)
    print(f"Collected {len(data)} jobs")
    for d in data:
        print(f"- {d['title']} | {d['budget_display']} | Match: {d.get('matched_keyword')} | {d['url']}")
