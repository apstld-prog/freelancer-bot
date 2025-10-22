#!/usr/bin/env python3
# platform_peopleperhour.py — Smart JSON scraping with true keyword match (ban-safe)
import httpx
import logging
import time
from datetime import datetime, timezone
from html import unescape

log = logging.getLogger("worker")

API_URL = "https://www.peopleperhour.com/graphql"
HEADERS = {
    "Content-Type": "application/json",
    "Origin": "https://www.peopleperhour.com",
    "Referer": "https://www.peopleperhour.com/freelance-jobs",
    "User-Agent": "Mozilla/5.0 (compatible; PPHBot/1.0; +https://freelancer-bot)"
}

# convert PPH date string (ISO) -> datetime UTC
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

def get_items(keywords):
    """Fetch PeoplePerHour jobs filtered by keyword list (true matches)."""
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
                "variables": {
                    "query": q,
                    "page": 1,
                    "filters": {},
                    "sort": "newest"
                },
                "query": """
                query SearchJobQuery($query: String, $page: Int, $filters: JobFilters, $sort: String) {
                  searchJobs(query: $query, page: $page, filters: $filters, sort: $sort) {
                    jobs {
                      id
                      title
                      description
                      currency
                      budget {
                        minimum
                        maximum
                      }
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

                    budget_min = _safe_float(j.get("budget", {}).get("minimum"))
                    budget_max = _safe_float(j.get("budget", {}).get("maximum"))
                    budget_currency = j.get("currency") or "GBP"

                    job = {
                        "title": title,
                        "description": desc[:1000],
                        "budget_min": budget_min,
                        "budget_max": budget_max,
                        "budget_currency": budget_currency,
                        "original_url": f"https://www.peopleperhour.com/freelance-jobs/{j.get('seoUrl')}",
                        "source": "PeoplePerHour",
                        "time_submitted": _to_dt(j.get("createdAt")),
                        "matched_keyword": q,
                    }
                    all_jobs.append(job)

                # Delay between keywords (safe rate limit)
                time.sleep(5)

            except Exception as e:
                log.warning("PPH error for %s: %s", q, e)
                continue

    log.info("PPH total merged: %d", len(all_jobs))
    return all_jobs


# --- ✅ Compatibility aliases for worker_runner ---
def fetch_pph_graphql(keywords):
    return get_items(keywords)

def fetch_pph_html(keywords):
    # fallback: reuse same fetcher for now
    return get_items(keywords)
