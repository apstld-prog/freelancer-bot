import os, time, logging, requests, re, unicodedata
from datetime import datetime, timezone
from db import get_session, get_all_users_with_keywords
from utils import send_job_to_user, usd_from_any
from db_events import record_event

log = logging.getLogger("worker.pph")

API_URL = "https://www.peopleperhour.com/api/v1/freelance-jobs"
FETCH_LIMIT = 30
CURRENCY_SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£"}

def normalize_text(s: str) -> str:
    if not s: return ""
    s = s.lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9\s]", " ", s)

def fetch_pph_jobs():
    r = requests.get(API_URL, timeout=20)
    r.raise_for_status()
    data = r.json()
    return data.get("results", [])

def format_job_card(job, matched_kw):
    title = job.get("title", "")
    desc = job.get("description", "")
    currency = job.get("currency", "GBP")
    amount = job.get("budget_minimum", 0)
    max_budget = job.get("budget_maximum", 0)
    usd_value = usd_from_any(amount, currency)
    budget_txt = f"{CURRENCY_SYMBOLS.get(currency, '')}{amount}–{max_budget} {currency}" if amount else "N/A"
    usd_txt = f" (~${usd_value:.0f} USD)" if usd_value else ""
    posted_str = job.get("posted_at") or job.get("published_at") or ""
    try:
        posted_dt = datetime.fromisoformat(posted_str.replace("Z", "+00:00"))
        diff = datetime.now(timezone.utc) - posted_dt
        posted_ago = f"{int(diff.total_seconds()//3600)}h ago"
    except Exception:
        posted_ago = "unknown"
    url = job.get("url") or job.get("permalink") or ""
    return (
        f"<b>{title}</b>\n"
        f"<b>Budget:</b> {budget_txt}{usd_txt}\n"
        f"<b>Source:</b> PeoplePerHour\n"
        f"<b>Match:</b> {matched_kw}\n"
        f"🕒 {posted_ago}\n"
        f"{desc[:500]}...\n"
        f"{url}"
    )

def main():
    log.info("[PPH] Fetch cycle start")
    try:
        jobs = fetch_pph_jobs()
        if not jobs:
            log.warning("No jobs fetched from PPH")
            return
        record_event("peopleperhour")
        with get_session() as s:
            users = get_all_users_with_keywords(s)
            for user in users:
                u_id, telegram_id, keywords = user
                norm_kws = [normalize_text(k) for k in keywords]
                for job in jobs:
                    text_all = normalize_text(f"{job.get('title','')} {job.get('description','')}")
                    matched_kw = next((kw for kw in norm_kws if kw in text_all), None)
                    if matched_kw:
                        try:
                            card = format_job_card(job, matched_kw)
                            send_job_to_user(telegram_id, card)
                            time.sleep(1)
                        except Exception as e:
                            log.exception("Send fail: %s", e)
        log.info("PPH cycle done.")
    except Exception as e:
        log.exception("[PPH] cycle error: %s", e)
