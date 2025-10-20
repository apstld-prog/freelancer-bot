import os
import time
import random
import datetime
import httpx
from bs4 import BeautifulSoup

# === Currency conversion table (approx.) ===
FX_RATES = {
    "USD": 1.0,
    "EUR": 1.08,
    "GBP": 1.26,
    "INR": 83.0,
    "AUD": 1.55,
    "CAD": 1.37,
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
]

def make_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
    }

def convert_to_usd(amount, currency):
    try:
        if not amount or not currency:
            return None
        rate = FX_RATES.get(currency.upper(), 1.0)
        return round(amount / rate, 2)
    except Exception:
        return None

def format_budget(min_val, max_val, currency):
    """Show local currency + USD conversion."""
    if not currency:
        return ""
    parts = []
    cur = currency.upper()

    # Build local currency range
    symbol = "$" if cur == "USD" else "€" if cur == "EUR" else "£" if cur == "GBP" else cur
    if min_val and max_val:
        local_str = f"{min_val:.0f}-{max_val:.0f} {symbol}"
    elif min_val:
        local_str = f"{min_val:.0f} {symbol}"
    else:
        local_str = f"{symbol}"

    # Convert to USD for display
    usd_min = convert_to_usd(min_val, cur)
    usd_max = convert_to_usd(max_val, cur)
    if usd_min and usd_max:
        usd_str = f"(~${usd_min}-{usd_max} USD)"
    elif usd_min:
        usd_str = f"(~${usd_min} USD)"
    else:
        usd_str = ""

    return f"{local_str} {usd_str}".strip()

def fetch_jobs(keywords, pages=5, delay=1.5):
    """Fetch job URLs from PeoplePerHour."""
    results = []
    for kw in keywords:
        for p in range(1, pages + 1):
            url = f"https://www.peopleperhour.com/freelance-jobs?q={kw}&page={p}"
            try:
                r = httpx.get(url, headers=make_headers(), timeout=20.0)
                if r.status_code == 403:
                    print(f"[PPH] kw={kw} p={p} blocked (HTTP 403) — pausing 30s")
                    time.sleep(30)
                    continue
                if r.status_code == 429:
                    print(f"[PPH] kw={kw} p={p} Too many requests — waiting 10s")
                    time.sleep(10)
                    continue
                if r.status_code != 200:
                    print(f"[PPH] kw={kw} p={p} HTTP {r.status_code}")
                    continue

                soup = BeautifulSoup(r.text, "html.parser")
                job_links = set()

                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if "/freelance-jobs/" in href and not href.endswith("/freelance-jobs"):
                        if not href.startswith("http"):
                            href = "https://www.peopleperhour.com" + href
                        job_links.add(href)

                print(f"[PPH] kw={kw} p={p} -> {len(job_links)} job links")
                for link in job_links:
                    results.append({"keyword": kw, "url": link})

                time.sleep(delay)
            except Exception as e:
                print(f"[PPH] Error on kw={kw} p={p}: {e}")
                time.sleep(5)
                continue

        print(f"[PPH] Finished keyword {kw}, waiting 15s")
        time.sleep(15)
    return results

def parse_job_page(url):
    """Parse each job page to extract title, description, and budget."""
    try:
        r = httpx.get(url, headers=make_headers(), timeout=20.0)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, "html.parser")
        title_el = soup.find("h1")
        desc_el = soup.find("div", {"class": "job-description"})

        budget_text = ""
        amount_min = amount_max = None
        currency = "USD"

        # Find Budget
        for span in soup.find_all(["span", "div"]):
            txt = span.get_text(strip=True)
            if "Budget" in txt or "$" in txt or "€" in txt or "£" in txt:
                budget_text = txt
                break

        if budget_text:
            currency = "USD"
            if "€" in budget_text:
                currency = "EUR"
            elif "£" in budget_text:
                currency = "GBP"
            elif "₹" in budget_text:
                currency = "INR"
            elif "AUD" in budget_text:
                currency = "AUD"

            nums = [
                float(x.replace(",", ""))
                for x in budget_text.replace("–", "-").replace("to", "-").split("-")
                if x.strip().replace(".", "").isdigit()
            ]
            if len(nums) == 1:
                amount_min = nums[0]
            elif len(nums) >= 2:
                amount_min, amount_max = nums[:2]

        budget_str = format_budget(amount_min, amount_max, currency)

        return {
            "title": title_el.get_text(strip=True) if title_el else "",
            "description": desc_el.get_text(strip=True) if desc_el else "",
            "budget_display": budget_str,
            "url": url,
        }
    except Exception:
        return None

def keyword_match(job, keywords):
    haystack = (job.get("title", "") + " " + job.get("description", "")).lower()
    for kw in keywords:
        if kw.lower() in haystack:
            job["matched_keyword"] = kw
            return True
    return False

def collect_pph_jobs(keywords):
    found = []
    jobs = fetch_jobs(keywords)
    for j in jobs:
        job_data = parse_job_page(j["url"])
        if not job_data:
            continue
        if keyword_match(job_data, keywords):
            found.append(job_data)
    print(f"[PPH] Cycle complete ({len(found)} matches). Waiting 60s before next run...")
    time.sleep(60)
    return found

def get_items(keywords=None):
    if not keywords:
        keywords = ["logo", "lighting", "luminaire"]
    return collect_pph_jobs(keywords)

if __name__ == "__main__":
    data = get_items(["logo", "lighting"])
    for d in data:
        print(f"- {d['title']} | {d['budget_display']} | Match: {d.get('matched_keyword')} | {d['url']}")
