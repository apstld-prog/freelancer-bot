# worker.py
import os
import time
import logging
import unicodedata
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import httpx

from db import (
    ensure_schema,
    SessionLocal,
    User,
    Keyword,
    JobSent,
)

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [db] %(levelname)s: %(message)s")
log = logging.getLogger("db")

# ---------------- Config (env) ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Cycle interval
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "300"))

# Freelancer
FREELANCER_REF_CODE = os.getenv("FREELANCER_REF_CODE", "").strip()  # e.g. apstld
FREELANCER_PROJECT_TYPE = os.getenv("FREELANCER_PROJECT_TYPE", "all").lower()  # all|fixed|hourly
FREELANCER_MIN_BUDGET = float(os.getenv("FREELANCER_MIN_BUDGET", "0"))
FREELANCER_MAX_BUDGET = float(os.getenv("FREELANCER_MAX_BUDGET", "0"))

# Matching behavior
JOB_MATCH_SCOPE = os.getenv("JOB_MATCH_SCOPE", "title_desc").lower()  # title | title_desc
JOB_MATCH_REQUIRE = os.getenv("JOB_MATCH_REQUIRE", "any").lower()     # any | all

# Optional: DM debug to admin
ADMIN_ID = os.getenv("ADMIN_ID", "").strip()
WORKER_DEBUG_TO_ADMIN = os.getenv("WORKER_DEBUG_TO_ADMIN", "0") == "1"

# Telegram API
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else None

UTC = timezone.utc
def now_utc() -> datetime:
    return datetime.now(UTC)

def to_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Return dt in UTC, making it timezone-aware if it was naive."""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    # unexpected type (e.g. string) -> ignore
    return None

# Ensure schema up-front
ensure_schema()

# ---------------- Normalization / Matching ----------------
def strip_accents(s: str) -> str:
    # accent-insensitive (works nicely for Greek)
    return "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")

def norm_text(s: str) -> str:
    if not s:
        return ""
    s = strip_accents(s)
    return s.casefold()

def job_matches(job: Dict, keywords: List[str], scope: str, require: str) -> Tuple[bool, List[str]]:
    """
    Return (ok, matched_keywords).
    - scope: 'title' or 'title_desc'
    - require: 'any' or 'all'
    """
    title = norm_text(job.get("title", ""))
    desc = norm_text(job.get("description", ""))

    haystack = title if scope == "title" else (title + " " + desc)

    matched = []
    for kw in keywords:
        kw_norm = norm_text(kw)
        if kw_norm and kw_norm in haystack:
            matched.append(kw)

    if require == "all":
        needed = [k for k in keywords if k.strip() != ""]
        ok = len(matched) == len(needed) and len(needed) > 0
    else:
        ok = len(matched) > 0
    return ok, matched

# ---------------- HTTP helpers ----------------
HTTP_TIMEOUT = 20.0

async def fetch_freelancer_projects(query: str) -> Dict:
    """
    Calls Freelancer public API for active projects.
    We ask wide and then we filter locally with job_matches().
    """
    url = (
        "https://www.freelancer.com/api/projects/0.1/projects/active/"
        f"?query={query}&limit=30&compact=true&user_details=true&job_details=true&full_description=true"
    )
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers={"Accept": "application/json"}) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()

def freelancer_job_to_card(p: Dict, matched: List[str]) -> Dict:
    pid = str(p.get("id"))
    title = p.get("title") or "Untitled"
    type_ = "Fixed" if p.get("type") == "fixed" else ("Hourly" if p.get("type") == "hourly" else "Unknown")
    budget = p.get("budget") or {}
    minb = budget.get("minimum") or 0
    maxb = budget.get("maximum") or 0
    bids = p.get("bid_stats", {}).get("bid_count", 0)
    time_submitted = p.get("time_submitted")
    posted = "now"
    if isinstance(time_submitted, (int, float)):
        age_sec = max(0, int(now_utc().timestamp() - time_submitted))
        if age_sec < 60:
            posted = f"{age_sec}s ago"
        elif age_sec < 3600:
            posted = f"{age_sec//60}m ago"
        elif age_sec < 86400:
            posted = f"{age_sec//3600}h ago"
        else:
            posted = f"{age_sec//86400}d ago"

    base_url = f"https://www.freelancer.com/projects/{pid}"
    sep = "&" if "?" in base_url else "?"
    job_url = f"{base_url}{sep}f={FREELANCER_REF_CODE}" if FREELANCER_REF_CODE else base_url

    desc = (p.get("description") or "").strip().replace("\r", " ").replace("\n", " ")
    if len(desc) > 220:
        desc = desc[:217] + "…"

    return {
        "id": f"freelancer-{pid}",
        "source": "Freelancer",
        "title": title,
        "type": type_,
        "budget_min": minb,
        "budget_max": maxb,
        "bids": bids,
        "posted": posted,
        "description": desc,
        "original_url": job_url,      # affiliate-safe
        "proposal_url": job_url,      # same for Freelancer
        "matched": matched,
    }

# ---------------- Telegram send ----------------
async def tg_send_message(chat_id: str, text: str, reply_markup: Optional[dict] = None):
    if not TG_API:
        return
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        r = await client.post(f"{TG_API}/sendMessage", json=payload)
        r.raise_for_status()

def job_markup(job: Dict) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "💼 Proposal", "url": job["proposal_url"]},
                {"text": "🔗 Original", "url": job["original_url"]},
            ],
            [
                {"text": "⭐ Keep", "callback_data": f"save:{job['id']}"},
                {"text": "🗑 Delete", "callback_data": f"dismiss:{job['id']}"},
            ],
        ]
    }

def job_text(job: Dict) -> str:
    budget_line = "—"
    if job["budget_min"] or job["budget_max"]:
        budget_line = f"{job['budget_min']:.0f}–{job['budget_max']:.0f}"
    matched_line = ", ".join(job.get("matched", [])) or "—"
    desc = job.get("description") or ""
    return (
        f"*{job['title']}*\n\n"
        f"👤 Source: *{job['source']}*\n"
        f"🧾 Type: *{job['type']}*\n"
        f"💰 Budget: *{budget_line}*\n"
        f"📨 Bids: *{job['bids']}*\n"
        f"🕒 Posted: *{job['posted']}*\n\n"
        f"{desc}\n\n"
        f"_Matched:_ {matched_line}"
    )

# ---------------- Core loop ----------------
async def process_user(db, u: User) -> int:
    """Returns number of messages sent for this user in this cycle."""
    if not u:
        return 0

    # --- FIX: make times timezone-aware before comparing ---
    now = now_utc()
    trial = to_aware(getattr(u, "trial_until", None))
    lic = to_aware(getattr(u, "access_until", None))

    active = False
    if trial and trial >= now:
        active = True
    if lic and lic >= now:
        active = True
    if not active:
        return 0

    # keywords
    kws_rows: List[Keyword] = u.keywords or []
    keywords = [k.keyword for k in kws_rows if (k.keyword or "").strip()]
    if not keywords:
        return 0

    # Build a wide query for the platform, then filter locally
    query_str = ",".join(keywords)

    # Fetch from Freelancer
    sent_count = 0
    try:
        data = await fetch_freelancer_projects(query_str)
        projects = (data.get("result") or {}).get("projects") or []
    except Exception as e:
        log.warning("Freelancer fetch error: %s", e)
        projects = []

    # budget/type coarse filter first
    filtered: List[Dict] = []
    for p in projects:
        # type
        ptype = p.get("type")
        if FREELANCER_PROJECT_TYPE == "fixed" and ptype != "fixed":
            continue
        if FREELANCER_PROJECT_TYPE == "hourly" and ptype != "hourly":
            continue
        # budget
        b = p.get("budget") or {}
        minb = float(b.get("minimum") or 0)
        maxb = float(b.get("maximum") or 0)
        if FREELANCER_MIN_BUDGET and maxb and maxb < FREELANCER_MIN_BUDGET:
            continue
        if FREELANCER_MAX_BUDGET and minb and minb > FREELANCER_MAX_BUDGET:
            continue
        filtered.append(p)

    # local keyword match (strict)
    strict: List[Tuple[Dict, List[str]]] = []
    for p in filtered:
        obj = {
            "title": p.get("title") or "",
            "description": p.get("description") or "",
        }
        ok, matched = job_matches(obj, keywords, JOB_MATCH_SCOPE, JOB_MATCH_REQUIRE)
        if ok:
            strict.append((p, matched))

    # dedup by project id & by previously sent
    already: Dict[str, bool] = {js.job_id: True for js in db.query(JobSent).filter_by(user_id=u.id).all()}

    for p, matched in strict:
        pid = str(p.get("id"))
        jid = f"freelancer-{pid}"
        if already.get(jid):
            continue

        job = freelancer_job_to_card(p, matched)
        text = job_text(job)
        markup = job_markup(job)

        try:
            await tg_send_message(u.telegram_id, text, markup)
            sent_count += 1
            db.add(JobSent(user_id=u.id, job_id=jid))
            db.commit()
            log.info("Sent job %s to %s", jid, u.telegram_id)
        except Exception as e:
            log.warning("Send error to %s: %s", u.telegram_id, e)

    return sent_count

async def worker_loop():
    log.info(
        "Worker loop every %ss (JOB_MATCH_SCOPE=%s, JOB_MATCH_REQUIRE=%s, FL_TYPE=%s, MIN=%.1f, MAX=%.1f)",
        WORKER_INTERVAL, JOB_MATCH_SCOPE, JOB_MATCH_REQUIRE,
        FREELANCER_PROJECT_TYPE, FREELANCER_MIN_BUDGET, FREELANCER_MAX_BUDGET
    )
    while True:
        db = SessionLocal()
        total_sent = 0
        try:
            users: List[User] = db.query(User).all()
            for u in users:
                total_sent += await process_user(db, u)
        except Exception as e:
            log.exception("Worker loop error: %s", e)
        finally:
            db.close()

        log.info("Worker cycle complete. Sent %d messages.", total_sent)

        # Optional debug DM to admin
        if WORKER_DEBUG_TO_ADMIN and TG_API and ADMIN_ID:
            try:
                await tg_send_message(
                    ADMIN_ID,
                    f"Worker cycle done. Sent *{total_sent}* messages.\n"
                    f"`scope={JOB_MATCH_SCOPE}, require={JOB_MATCH_REQUIRE}`",
                )
            except Exception:
                pass

        time.sleep(WORKER_INTERVAL)

# ---------------- Entrypoint ----------------
if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(worker_loop())
    except KeyboardInterrupt:
        pass
