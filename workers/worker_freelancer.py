import os, time, logging, requests, re, unicodedata
from datetime import datetime, timezone
from db import get_session, get_all_users_with_keywords
from utils import send_job_to_user, usd_from_any
from db_events import record_event

log = logging.getLogger("worker.freelancer")

API_URL = "https://www.freelancer.com/api/projects/0.1/projects/active/"
FETCH_LIMIT = 30
CURRENCY_SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£"}

def normalize_text(s: str) -> str:
    if not s: return ""
    s = s.lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9\s]", " ", s)

def fetch_freelancer_jobs():
    params = {
        "full_description": False,
        "job_details": False,
        "limit": FETCH_LIMIT,
        "offset": 0,
        "sort_field": "time_submitted",
        "sort_direction": "desc",
    }
    r = requests.get(API_URL, params=params, timeout=20)
    r.raise_for_status()
    return r.json().get("result", {}).get("projects", [])

def format_job_card(job, matched_kw):
    title = job.get("title", "").strip()
    desc = job.get("preview_description", "")
    budget = job.get("budget", {}) or {}
    amount = budget.get("minimum", 0)
    maximum = budget.get("maximum", 0)
    currency = budget.get("currency", {}).get("code", "USD")
    usd_value = usd_from_any(amount, currency)
    posted_ts = job.get("submitdate")
    if posted_ts:
        diff = datetime.now(timezone.utc) - datetime.fromtimestamp(posted_ts, tz=timezone.utc)
        posted_ago = f"{int(diff.total_seconds()//3600)}h ago"
    else:
        posted_ago = "unknown"
    currency_symbol = CURRENCY_SYMBOLS.get(currency, "")
    if amount and maximum:
        budget_txt = f"{currency_symbol}{amount}–{maximum} {currency}"
    elif amount:
        budget_txt = f"{currency_symbol}{amount} {currency}"
    else:
        budget_txt = "N/A"
    usd_txt = f" (~${usd_value:.0f} USD)" if usd_value else ""
    url = f"https://www.freelancer.com/projects/{job.get('seo_url','') or job.get('id')}"
    return (
        f"<b>{title}</b>\n"
        f"<b>Budget:</b> {budget_txt}{usd_txt}\n"
        f"<b>Source:</b> Freelancer\n"
        f"<b>Match:</b> {matched_kw}\n"
        f"🕒 {posted_ago}\n"
        f"{desc[:500]}...\n"
        f"{url}"
    )

def main():
    log.info("[Freelancer] Fetch cycle start")
    try:
        jobs = fetch_freelancer_jobs()
        if not jobs:
            log.warning("No jobs fetched from Freelancer")
            return
        record_event("freelancer")
        with get_session() as s:
            users = get_all_users_with_keywords(s)
            for user in users:
                u_id, telegram_id, keywords = user
                norm_kws = [normalize_text(k) for k in keywords]
                for job in jobs:
                    title = job.get("title", "")
                    desc = job.get("preview_description", "")
                    norm_text = normalize_text(f"{title} {desc}")
                    matched_kw = next((kw for kw in norm_kws if kw in norm_text), None)
                    if matched_kw:
                        try:
                            card = format_job_card(job, matched_kw)
                            send_job_to_user(telegram_id, card)
                            time.sleep(1)
                        except Exception as e:
                            log.exception("Send fail: %s", e)
        log.info("Freelancer cycle done.")
    except Exception as e:
        log.exception("[Freelancer] cycle error: %s", e)
