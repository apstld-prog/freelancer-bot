import httpx
import asyncio
import logging
import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

log = logging.getLogger("platform_peopleperhour")

BASE_URL = "https://www.peopleperhour.com/freelance-jobs"
PROXY_URL = "https://pph-proxy-service.onrender.com/api/pph"

async def fetch_peopleperhour_jobs(keyword):
    """Fetch jobs from PeoplePerHour (proxy or HTML fallback)."""
    jobs = []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            url = f"{PROXY_URL}?key=1211&q={keyword}"
            r = await client.get(url)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict):
                    data = data.get("jobs", [])
                elif not isinstance(data, list):
                    data = []

                if not data:
                    log.info(f"⚠️ Proxy empty → fallback to HTML for '{keyword}'")
                    html = await client.get(f"{BASE_URL}?q={keyword}")
                    soup = BeautifulSoup(html.text, "html.parser")
                    cards = soup.find_all("section", class_="job-tile")

                    for c in cards:
                        title_tag = c.find("a", class_="job-tile-title")
                        title = title_tag.text.strip() if title_tag else ""
                        link = title_tag["href"] if title_tag and title_tag.get("href") else ""
                        link = link if link.startswith("http") else f"https://www.peopleperhour.com{link}"
                        desc = c.find("p", class_="job-tile-description")
                        desc = desc.text.strip() if desc else ""
                        budget_tag = c.find("span", class_="job-tile-budget")
                        budget_text = budget_tag.text.strip() if budget_tag else ""
                        m = re.findall(r"([\d\.]+)", budget_text)
                        budget = float(m[0]) if m else 0.0
                        currency = "GBP" if "£" in budget_text else "EUR" if "€" in budget_text else "USD"
                        ts = datetime.now(tz=timezone.utc).timestamp()
                        job = {
                            "title": title,
                            "description": desc,
                            "original_url": link,
                            "affiliate_url": link,
                            "budget_amount": budget,
                            "budget_currency": currency,
                            "source": "PeoplePerHour",
                            "timestamp": ts,
                        }
                        jobs.append(job)
                else:
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
                            else:
                                ts = datetime.now(tz=timezone.utc).timestamp()
                            clean_budget = 0
                            if isinstance(budget, (int, float)):
                                clean_budget = float(budget)
                            elif isinstance(budget, str):
                                m = re.findall(r"[\d\.]+", budget)
                                if m:
                                    clean_budget = float(m[0])
                            job = {
                                "title": title,
                                "description": desc,
                                "original_url": link,
                                "affiliate_url": link,
                                "budget_amount": clean_budget,
                                "budget_currency": currency,
                                "source": "PeoplePerHour",
                                "timestamp": ts,
                            }
                            jobs.append(job)
                        except Exception as e:
                            log.warning(f"[PPH parse error] {e}")

                # ✅ Φιλτράρουμε αγγελίες έως 48 ωρών
                cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=48)
                jobs = [j for j in jobs if datetime.fromtimestamp(j["timestamp"], tz=timezone.utc) >= cutoff]

            else:
                log.warning(f"[PPH] Status {r.status_code} for '{keyword}'")
    except Exception as e:
        log.warning(f"[PPH error] {e}")

    log.info(f"[PPH total merged: {len(jobs)}]")
    return jobs


async def fetch_pph_jobs(keywords):
    """Wrapper για το fetch_peopleperhour_jobs."""
    if isinstance(keywords, list):
        results = []
        for kw in keywords:
            jobs = await fetch_peopleperhour_jobs(kw)
            results.extend(jobs)
        return results
    else:
        return await fetch_peopleperhour_jobs(str(keywords))
