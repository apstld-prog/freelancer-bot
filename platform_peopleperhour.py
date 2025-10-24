import httpx
import asyncio
import logging
import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone

log = logging.getLogger("platform_peopleperhour")

BASE_URL = "https://www.peopleperhour.com/freelance-jobs"
PROXY_URL = "https://pph-proxy-service.onrender.com/api/pph"

async def fetch_peopleperhour_jobs(keyword):
    """Fetch jobs from PeoplePerHour for a specific keyword"""
    jobs = []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            url = f"{PROXY_URL}?key=1211&q={keyword}"
            r = await client.get(url)
            if r.status_code == 200:
                data = r.json()

                # ✅ Handle both list and dict-based responses
                if isinstance(data, dict):
                    data = data.get("jobs", [])
                elif not isinstance(data, list):
                    data = []

                if not data:
                    log.info(f"⚠️ No PPH results for keyword '{keyword}'")

                for j in data:
                    try:
                        title = str(j.get("title", "")).strip()
                        link = j.get("url") or ""
                        if not isinstance(link, str):
                            link = str(link)

                        desc = str(j.get("description", "")).strip()
                        budget = j.get("budget") or ""
                        currency = str(j.get("currency", "")).strip() or "GBP"
                        posted = j.get("posted") or ""
                        ts = None
                        if posted:
                            try:
                                ts = datetime.fromisoformat(posted.replace("Z", "+00:00")).timestamp()
                            except Exception:
                                ts = datetime.now(tz=timezone.utc).timestamp()

                        # ✅ Καθαρό parsing προϋπολογισμού
                        clean_budget = 0
                        bmin, bmax = 0, 0
                        if isinstance(budget, (int, float)):
                            clean_budget = float(budget)
                        elif isinstance(budget, str):
                            m = re.findall(r"[\d\.]+", budget)
                            if len(m) == 1:
                                clean_budget = float(m[0])
                            elif len(m) == 2:
                                bmin, bmax = map(float, m)

                        job = {
                            "title": title,
                            "description": desc,
                            "original_url": link,
                            "affiliate_url": link,
                            "budget_amount": clean_budget,
                            "budget_min": bmin,
                            "budget_max": bmax,
                            "budget_currency": currency,
                            "source": "PeoplePerHour",
                            "timestamp": ts,
                        }
                        jobs.append(job)
                    except Exception as e:
                        log.warning(f"[PPH parse error] {e}")
            else:
                log.warning(f"[PPH] Status {r.status_code} for '{keyword}'")
    except Exception as e:
        log.warning(f"[PPH error] {e}")
    log.info(f"[PPH total merged: {len(jobs)}]")
    return jobs


# -----------------------------
# ✅ Alias για συμβατότητα με worker_runner
# -----------------------------
async def fetch_pph_jobs(keywords):
    """Wrapper για το fetch_peopleperhour_jobs (δέχεται είτε λίστα είτε string keywords)."""
    if isinstance(keywords, list):
        results = []
        for kw in keywords:
            jobs = await fetch_peopleperhour_jobs(kw)
            results.extend(jobs)
        return results
    else:
        return await fetch_peopleperhour_jobs(str(keywords))
