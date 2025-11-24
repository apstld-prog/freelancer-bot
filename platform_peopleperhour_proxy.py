# platform_peopleperhour_proxy.py — FINAL PPH PROXY CLIENT
# -------------------------------------------------------
# Συνδέεται με το pph-proxy (Docker service)
# Κάνει request στο /jobs?kw=...
# Παίρνει JSON (ή fallback HTML)
# Επιστρέφει unified items, με matched_keyword
# -------------------------------------------------------

import httpx
from bs4 import BeautifulSoup

BASE = "https://pph-proxy.onrender.com"


def _fetch_json(kw: str):
    """Προσπαθεί να πάρει JSON από /jobs?kw=..."""
    try:
        r = httpx.get(f"{BASE}/jobs", params={"kw": kw}, timeout=20)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            return data
    except Exception:
        return None
    return None


def _fetch_html(kw: str):
    """Fallback: παίρνει HTML από /jobs_html?kw=..."""
    try:
        r = httpx.get(f"{BASE}/jobs_html", params={"kw": kw}, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception:
        return []

    jobs = []
    tiles = soup.select(".job-tile")
    for t in tiles:
        title = t.select_one(".job-title")
        desc = t.select_one(".job-description")
        jobs.append({
            "title": title.get_text(strip=True) if title else "",
            "description": desc.get_text(strip=True) if desc else "",
            "source": "peopleperhour"
        })
    return jobs


def fetch(kw: str):
    """Κάνει JSON first, μετά HTML fallback."""
    if not kw:
        return []

    # 1) JSON first
    data = _fetch_json(kw)
    if data:
        # JSON job objects πρέπει να είναι ήδη καθαρά
        cleaned = []
        for j in data:
            title = j.get("title", "")
            desc = j.get("description", "")
            cleaned.append({
                "title": title,
                "description": desc,
                "source": "peopleperhour"
            })
        return cleaned

    # 2) HTML fallback
    return _fetch_html(kw)


def get_items(keywords):
    """Καλείται από τον worker. Επιστρέφει matched items."""
    out = []
    for kw in keywords:
        kw_clean = kw.strip().lower()
        if not kw_clean:
            continue

        jobs = fetch(kw_clean)
        for job in jobs:
            title = (job.get("title") or "").lower()
            desc = (job.get("description") or "").lower()
            if kw_clean in title or kw_clean in desc:
                x = job.copy()
                x["matched_keyword"] = kw
                out.append(x)

    return out
