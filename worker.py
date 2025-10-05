import os
import asyncio
import logging
from datetime import timedelta
from typing import Dict, Any, List, Optional

import httpx

from db import (
    get_session, now_utc,
    User, Keyword, Job, JobSent
)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("db")

INTERVAL = int(os.getenv("WORKER_INTERVAL_SECONDS", "120"))

# Feature toggles
ENABLE_FREELANCER = os.getenv("ENABLE_FREELANCER", "1") == "1"
ENABLE_PPH = os.getenv("ENABLE_PPH", "1") == "1"
ENABLE_KARIERA = os.getenv("ENABLE_KARIERA", "1") == "1"
ENABLE_JOBFIND = os.getenv("ENABLE_JOBFIND", "0") == "1"

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Affiliate
AFFILIATE_FREELANCER_REF = os.getenv("AFFILIATE_FREELANCER_REF", "")
AFFILIATE_FIVERR_BTA = os.getenv("AFFILIATE_FIVERR_BTA", "")

# Matching mode
JOB_MATCH_SCOPE = os.getenv("JOB_MATCH_SCOPE", "title_desc")  # title | title_desc
JOB_MATCH_REQUIRE = os.getenv("JOB_MATCH_REQUIRE", "any")     # any | all

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
_http = httpx.AsyncClient(timeout=20)

async def tg_send(chat_id: int, text: str, reply_markup: Optional[Dict[str, Any]] = None, parse_mode: Optional[str] = "Markdown"):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode
    r = await _http.post(f"{API_BASE}/sendMessage", json=payload)
    r.raise_for_status()
    log.info("HTTP Request: POST %s/sendMessage %s", f"{API_BASE}", r.reason_phrase)

def aff_wrap(source: str, url: str) -> str:
    if source == "freelancer" and AFFILIATE_FREELANCER_REF:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}referrer={AFFILIATE_FREELANCER_REF}"
    return url

# ---------------------------------------------------------------------------
# Fetchers (συντομευμένα placeholders – κράτα τα δικά σου αν τα έχεις ήδη)
# ---------------------------------------------------------------------------
async def freelancer_search(q: str) -> List[Dict[str, Any]]:
    params = {
        "query": q,
        "limit": 30,
        "compact": "true",
        "user_details": "true",
        "job_details": "true",
        "full_description": "true",
    }
    url = "https://www.freelancer.com/api/projects/0.1/projects/active/"
    r = await _http.get(url, params=params)
    if r.status_code != 200:
        log.warning("Freelancer fetch error for '%s': %s", q, r.text)
        return []
    data = r.json()
    projects = data.get("result", {}).get("projects", []) or []
    jobs = []
    for p in projects:
        jid = str(p.get("id"))
        title = p.get("title") or "No title"
        desc = p.get("preview_description") or p.get("description") or ""
        link = f"https://www.freelancer.com/projects/{jid}"
        budget = p.get("budget") or {}
        bmin = budget.get("minimum")
        bmax = budget.get("maximum")
        curr = budget.get("currency", {}).get("code") or "USD"
        bids = p.get("bid_stats", {}).get("bid_count")
        jobs.append({
            "source": "freelancer",
            "source_id": jid,
            "title": title,
            "description": desc,
            "url": link,
            "budget_min": bmin,
            "budget_max": bmax,
            "budget_currency": curr,
            "job_type": "fixed",
            "bids_count": bids,
        })
    return jobs

async def pph_search(q: str) -> List[Dict[str, Any]]:
    # Απλό HTML listing parser-less: θα δώσει λίγη κάλυψη· οι πραγματικές αγγελίες θέλουν parsing
    url = f"https://www.peopleperhour.com/freelance-jobs?q={httpx.utils.quote(q) if hasattr(httpx, 'utils') else httpx.QueryParams({'q': q})['q']}"
    r = await _http.get(url, follow_redirects=True)
    if r.status_code != 200:
        log.info("PPH '%s': %s", q, r.status_code)
        return []
    # Αν δεν κάνεις parsing, γύρνα άδειο για να μη σπαμάρει
    return []

async def kariera_search(q: str) -> List[Dict[str, Any]]:
    url = f"https://www.kariera.gr/jobs?keyword={q}"
    r = await _http.get(url, follow_redirects=True)
    if r.status_code != 200:
        return []
    # Χωρίς parsing → επέστρεψε κενό για να μην έρχονται άσχετα
    return []

# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------
def matches(job: Dict[str, Any], kws: List[str]) -> Optional[str]:
    title = (job.get("title") or "").lower()
    desc  = (job.get("description") or "").lower()
    text = f"{title}\n{desc}" if JOB_MATCH_SCOPE == "title_desc" else title

    if JOB_MATCH_REQUIRE == "all":
        ok = all(k in text for k in kws)
        if ok:
            return ",".join(kws)
        return None
    else:
        for k in kws:
            if k in text:
                return k
        return None

# ---------------------------------------------------------------------------
# Main per-user processing
# ---------------------------------------------------------------------------
async def process_user(db_session, u: User) -> int:
    if u.is_blocked:
        return 0
    now = now_utc()
    trial_ok = u.trial_until and u.trial_until >= now
    license_ok = u.access_until and u.access_until >= now
    if not (trial_ok or license_ok):
        return 0

    kws = [k.keyword for k in u.keywords]
    if not kws:
        return 0

    sent = 0
    all_jobs: List[Dict[str, Any]] = []

    for kw in kws:
        if ENABLE_FREELANCER:
            all_jobs += await freelancer_search(kw)
        if ENABLE_PPH:
            all_jobs += await pph_search(kw)
        if ENABLE_KARIERA:
            all_jobs += await kariera_search(kw)
        # ENABLE_JOBFIND αφήνεται off μέχρι να σταθεροποιηθεί endpoint

    # Αποθήκευση/αφαίρεση διπλών με βάση (source, source_id)
    seen = set()
    unique_jobs = []
    for j in all_jobs:
        key = (j.get("source"), j.get("source_id"))
        if key in seen:
            continue
        seen.add(key)
        unique_jobs.append(j)

    # Match per user
    for j in unique_jobs:
        mk = matches(j, kws)
        if not mk:
            continue

        # upsert στην Job
        job_row = db_session.query(Job).filter(
            Job.source == j["source"], Job.source_id == j.get("source_id")
        ).one_or_none()
        if not job_row:
            job_row = Job(
                source=j["source"], source_id=j.get("source_id"),
                title=j["title"], description=j.get("description"),
                url=j["url"], proposal_url=None, original_url=j["url"],
                budget_min=j.get("budget_min"), budget_max=j.get("budget_max"),
                budget_currency=j.get("budget_currency"), job_type=j.get("job_type"),
                bids_count=j.get("bids_count"), matched_keyword=mk, posted_at=now_utc()
            )
            db_session.add(job_row)
            db_session.flush()
        else:
            job_row.matched_keyword = mk
            job_row.updated_at = now_utc()
            db_session.flush()

        # anti-duplication per user
        already = db_session.query(JobSent).filter(
            JobSent.user_id == u.id, JobSent.job_id == job_row.id
        ).one_or_none()
        if already:
            continue

        # affiliate links
        prop = aff_wrap(j["source"], j["url"])
        orig = aff_wrap(j["source"], j["url"])
        job_row.proposal_url = prop
        job_row.original_url = orig

        # build message
        budget_line = ""
        bmin = j.get("budget_min"); bmax = j.get("budget_max"); cur = j.get("budget_currency") or ""
        if bmin or bmax:
            rng = f"{bmin or ''}–{bmax or ''} {cur}".strip("– ").strip()
            budget_line = f"\n💲 Budget: {rng}"

        text = (
            f"*{j['title']}*\n"
            f"Source: {j['source']}{budget_line}\n"
            f"Matched keyword: `{mk}`\n\n"
            f"{(j.get('description') or '')[:400]}…"
        )
        kb = {
            "inline_keyboard": [
                [
                    {"text": "📦 Proposal", "url": prop},
                    {"text": "🔗 Original", "url": orig},
                ],
                [
                    {"text": "⭐ Keep", "callback_data": f"keep:{job_row.id}"},
                    {"text": "🗑️ Delete", "callback_data": f"del:{job_row.id}"},
                ],
            ]
        }
        await tg_send(int(u.telegram_id), text, reply_markup=kb, parse_mode="Markdown")

        db_session.add(JobSent(user_id=u.id, job_id=job_row.id))
        db_session.flush()
        sent += 1

    return sent

# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------
async def worker_loop():
    while True:
        try:
            total = 0
            with get_session() as db:
                users = db.query(User).all()
                for u in users:
                    total += await process_user(db, u)
            log.info("Worker cycle complete. Sent %d messages.", total)
        except Exception as e:
            log.exception("Worker loop error: %s", e)
        await asyncio.sleep(INTERVAL)

if __name__ == "__main__":
    log.info(
        "Worker loop every %ss (JOB_MATCH_SCOPE=%s, JOB_MATCH_REQUIRE=%s, "
        "FL_TYPE=all, MIN=0.0, MAX=0.0)",
        INTERVAL, JOB_MATCH_SCOPE, JOB_MATCH_REQUIRE
    )
    asyncio.run(worker_loop())
