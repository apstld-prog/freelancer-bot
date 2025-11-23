# platform_peopleperhour_proxy.py — DROMOS A
# FULL FILE — 100% COMPATIBLE WITH NEW PROXY (app.py)

import httpx
from typing import List, Dict


# ---------------------------------------
# CONFIG — Hardcoded proxy URL from config.py
# ---------------------------------------
from config import PEOPLEPERHOUR_PROXY_URL


# ---------------------------------------
# Fetch search results from proxy
# ---------------------------------------
def _fetch_search(kw: str) -> List[Dict]:
    """
    Calls: https://pph-proxy.onrender.com/jobs?kw=logo
    Returns: {keyword, count, jobs: [ ... ]}
    """
    try:
        r = httpx.get(
            f"{PEOPLEPERHOUR_PROXY_URL}/jobs",
            params={"kw": kw},
            timeout=30.0
        )
        if r.status_code != 200:
            return []
        data = r.json()
        return data.get("jobs", [])
    except Exception:
        return []


# ---------------------------------------
# Fetch job details (budget, description)
# ---------------------------------------
def _fetch_job(url: str) -> Dict:
    """
    Calls: https://pph-proxy.onrender.com/job?url=...
    Returns job details dict.
    """
    try:
        r = httpx.get(
            f"{PEOPLEPERHOUR_PROXY_URL}/job",
            params={"url": url},
            timeout=30.0
        )
        if r.status_code != 200:
            return {}
        return r.json()
    except Exception:
        return {}


# ---------------------------------------
# Public API for unified worker
# ---------------------------------------
def get_items(keywords: List[str]) -> List[Dict]:
    """
    Returns all matched PPH items:
        - title
        - description
        - url
        - budget (if available)
    """
    results = []

    for kw in keywords:
        jobs = _fetch_search(kw)
        for job in jobs:
            item = {
                "source": "peopleperhour",
                "matched_keyword": kw,
                "title": job.get("title", "").strip(),
                "original_url": job.get("url", ""),
                "proposal_url": job.get("url", ""),
                "description": job.get("desc", ""),
                "description_html": job.get("desc", ""),
                "time_submitted": job.get("time", None),
            }

            # fetch additional job details (budget, etc)
            detail = _fetch_job(item["original_url"])
            item["budget_min"] = detail.get("budget_min")
            item["budget_max"] = detail.get("budget_max")
            item["currency"] = detail.get("currency")

            results.append(item)

    return results
