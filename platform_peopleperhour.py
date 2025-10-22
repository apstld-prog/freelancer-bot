#!/usr/bin/env python3
# platform_peopleperhour.py — Smart keyword fetcher (GraphQL + HTML fallback)
import httpx, logging, time
from datetime import datetime, timezone
from html import unescape
from bs4 import BeautifulSoup

log = logging.getLogger("worker")

API_URL = "https://www.peopleperhour.com/graphql"
HEADERS = {
    "Content-Type": "application/json",
    "Origin": "https://www.peopleperhour.com",
    "Referer": "https://www.peopleperhour.com/freelance-jobs",
    "User-Agent": "Mozilla/5.0 (compatible; PPHBot/1.0; +https://freelancer-bot)"
}

def _to_dt(s: str):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)

def _safe_float(v):
    try:
        return float(v)
    except Exception:
        return None

def fetch_pph_graphql(keywords):
    """Primary: GraphQL API query (safe + structured)."""
    all_jobs = []
    if not keywords:
        return all_jobs

    with httpx.Client(timeout=30) as client:
        for kw in keywords:
            q = kw.strip()
            if not q:
                continue

            payload = {
                "operationName": "SearchJobQuery",
                "variables": {"query": q, "page": 1, "filters": {}, "sort": "newest"},
                "query": """
                query SearchJobQuery($query: String, $page: Int, $filters: JobFilters, $sort: String) {
                  searchJobs(query: $query, page: $page, filters: $filters, sort: $sort) {
                    jobs {
                      id
                      title
                      description
                      currency
                      budget { minimum maximum }
                      seoUrl
                      createdAt
                    }
                  }
                }"""
            }

            try:
                r = client.post(API_URL, headers=HEADERS, json=payload)
                if r.status_code != 200:
                    log.warning("PPH GraphQL HTTP %s for %s", r.status_code, q)
                    continue

                data = r.json()
                jobs = data.get("data", {}).get("searchJobs", {}).get("jobs", [])
                log.info("PPH found %d jobs for keyword=%s", len(jobs), q)

                for j in jobs:
                    title = unescape((j.get("title") or "").strip())
                    desc = unescape((j.get("description") or "").strip())
                    if not title or not desc:
                        continue

                    hay = f"{title.lower()} {desc.lower()}"
                    if q.lower() not in hay:
                        continue

                    all_jobs.append({
                        "title": title,
                        "description": desc[:1000],
                        "budget_min": _safe_float(j.get("budget", {}).get("minimum")),
                        "budget_max": _safe_float(j.get("budget", {}).get("maximum")),
                        "budget_currency": j.get("currency") or "GBP",
                        "original_url": f"https://www.peopleperhour.com/freelance-jobs/{j.get('seoUrl')}",
                        "source": "PeoplePerHour",
                        "time_submitted": _to_dt(j.get("createdAt")),
                        "matched_keyword": q,
                    })
                time.sleep(5)
            except Exception as e:
                log.warning("PPH GraphQL error for %s: %s", q, e)
                continue
    return all_jobs

def fetch_pph_html(keywords):
    """Fallback HTML scraper for when GraphQL returns 404 or empty."""
    all_jobs = []
    if not keywords:
        return all_jobs

    with httpx.Client(timeout=30) as client:
        for kw in keywords:
            q = kw.strip()
            if not q:
                continue

            try:
                url = f"https://www.peopleperhour.com/freelance-jobs?q={q}"
                r = client.get(url, headers=HEADERS)
                if r.status_code != 200:
                    log.warning("PPH HTML HTTP %s for %s", r.status_code, q)
                    continue

                soup = BeautifulSoup(r.text, "html.parser")
                cards = soup.select("section[data-job-id]")
                for c in cards:
                    title_el = c.select_one("h5")
                    desc_el = c.select_one("p")
                    budget_el = c.select_one("span.job-price")
                    link_el = c.select_one("a")
                    if not title_el or not link_el:
                        continue

                    title = unescape(title_el.get_text(strip=True))
                    desc = unescape(desc_el.get_text(strip=True)) if desc_el else ""
                    url = "https://www.peopleperhour.com" + link_el.get("href", "")
                    budget_text = (budget_el.get_text(strip=True) if budget_el else "").replace(",", "")
                    budget_min = budget_max = None
                    currency = "GBP"
                    if "£" in budget_text:
                        currency = "GBP"
                        budget_text = budget_text.replace("£", "")
                    try:
                        if "-" in budget_text:
                            parts = budget_text.split("-")
                            budget_min = float(parts[0])
                            budget_max = float(parts[1])
                        else:
                            budget_min = float(budget_text)
                    except Exception:
                        pass

                    all_jobs.append({
                        "title": title,
                        "description": desc[:1000],
                        "budget_min": budget_min,
                        "budget_max": budget_max,
                        "budget_currency": currency,
                        "original_url": url,
                        "source": "PeoplePerHour",
                        "time_submitted": datetime.now(timezone.utc),
                        "matched_keyword": q,
                    })
                time.sleep(5)
            except Exception as e:
                log.warning("PPH HTML error for %s: %s", q, e)
                continue
    return all_jobs

# --- ✅ Compatibility wrappers ---
def get_items(keywords):
    jobs = fetch_pph_graphql(keywords)
    if not jobs:
        jobs = fetch_pph_html(keywords)
    log.info("PPH total merged: %d", len(jobs))
    return jobs
