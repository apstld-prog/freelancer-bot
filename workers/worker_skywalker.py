import os, time, logging, requests, re, unicodedata
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from db import get_session, get_all_users_with_keywords
from utils import send_job_to_user
from db_events import record_event

log = logging.getLogger("worker.skywalker")

BASE_URL = "https://www.skywalker.gr/elGR/aggelies"
CURRENCY_SYMBOLS = {"EUR": "€"}

def normalize_text(s: str) -> str:
    if not s: return ""
    s = s.lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9\s]", " ", s)

def fetch_skywalker_jobs():
    r = requests.get(BASE_URL, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    jobs = []
    for a in soup.select(".job"):
        title = a.select_one(".job-title")
        href = a.get("href", "")
        desc = a.text.strip()
        if title:
            jobs.append({
                "title": title.text.strip(),
                "url": f"https://www.skywalker.gr{href}" if href.startswith("/") else href,
                "desc": desc
            })
    return jobs

def format_job_card(job, matched_kw):
    title = job.get("title", "")
    url = job.get("url", "")
    desc = job.get("desc", "")
    return (
        f"<b>{title}</b>\n"
        f"<b>Source:</b> Skywalker\n"
        f"<b>Match:</b> {matched_kw}\n"
        f"{desc[:500]}...\n"
        f"{url}"
    )

def main():
    log.info("[Skywalker] Fetch cycle start")
    try:
        jobs = fetch_skywalker_jobs()
        if not jobs:
            log.warning("No jobs fetched from Skywalker")
            return
        record_event("skywalker")
        with get_session() as s:
            users = get_all_users_with_keywords(s)
            for user in users:
                u_id, telegram_id, keywords = user
                norm_kws = [normalize_text(k) for k in keywords]
                for job in jobs:
                    norm_text = normalize_text(f"{job.get('title','')} {job.get('desc','')}")
                    matched_kw = next((kw for kw in norm_kws if kw in norm_text), None)
                    if matched_kw:
                        try:
                            card = format_job_card(job, matched_kw)
                            send_job_to_user(telegram_id, card)
                            time.sleep(1)
                        except Exception as e:
                            log.exception("Send fail: %s", e)
        log.info("Skywalker cycle done.")
    except Exception as e:
        log.exception("[Skywalker] cycle error: %s", e)
