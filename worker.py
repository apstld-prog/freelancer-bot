# worker.py
# Drop-in: keeps your existing behavior, adds publish_stats() at the end of each loop.
import os
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import httpx

from db import (
    get_session,
    now_utc,
    User,
    Keyword,
    Job,
    JobSent,
)
from currency import usd_convert  # your existing helper (no changes)
from worker_stats_sidecar import publish_stats  # NEW: sidecar stats publisher

log = logging.getLogger("db")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

# ---------- Env toggles (no behavior change) ----------
ENABLE_FREELANCER   = os.getenv("ENABLE_FREELANCER",   "1") == "1"
ENABLE_PPH          = os.getenv("ENABLE_PPH",          "1") == "1"
ENABLE_KARIERA      = os.getenv("ENABLE_KARIERA",      "1") == "1"
ENABLE_JOBFIND      = os.getenv("ENABLE_JOBFIND",      "0") == "1"
ENABLE_TWAGO        = os.getenv("ENABLE_TWAGO",        "1") == "1"
ENABLE_FREELANCERMAP= os.getenv("ENABLE_FREELANCERMAP","1") == "1"
ENABLE_YUNOJUNO     = os.getenv("ENABLE_YUNOJUNO",     "1") == "1"
ENABLE_WORKSOME     = os.getenv("ENABLE_WORKSOME",     "1") == "1"
ENABLE_CODEABLE     = os.getenv("ENABLE_CODEABLE",     "1") == "1"
ENABLE_GURU         = os.getenv("ENABLE_GURU",         "1") == "1"
ENABLE_99DESIGNS    = os.getenv("ENABLE_99DESIGNS",    "1") == "1"

WORKER_INTERVAL_SEC = int(os.getenv("WORKER_INTERVAL_SEC", "120"))
TELEGRAM_BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")

# ---------- Telegram send helper (unchanged behavior) ----------
async def tg_send(chat_id: int, text: str, reply_markup: Optional[dict]=None, parse_mode: Optional[str]="Markdown"):
    api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(api, json=payload)
        log.info("HTTP Request: POST %s %s", api, r.status_code)
        r.raise_for_status()
        return r.json()

# ---------- Feed helpers (same signatures; keep your internals) ----------
FREELANCER_API = "https://www.freelancer.com/api/projects/0.1/projects/active/"

async def freelancer_search(q: str) -> List[dict]:
    if not ENABLE_FREELANCER:
        return []
    params = {
        "query": q,
        "limit": 30,
        "compact": "true",
        "user_details": "true",
        "job_details": "true",
        "full_description": "true",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(FREELANCER_API, params=params)
        log.info("HTTP Request: GET %s %s", r.request.url, r.status_code)
        r.raise_for_status()
        data = r.json()
    # προσαρμόσου στο δικό σου mapping -> list[jobdict]
    projects = data.get("result", {}).get("projects", []) or []
    out = []
    for p in projects:
        out.append({
            "source": "freelancer",
            "external_id": str(p.get("id")),
            "title": p.get("title") or "",
            "description": p.get("description") or "",
            "url": f"https://www.freelancer.com/projects/{p.get('id')}",
            "proposal_url": None,
            "original_url": f"https://www.freelancer.com/projects/{p.get('id')}",
            "budget_min": float(p.get("budget", {}).get("minimum", 0) or 0),
            "budget_max": float(p.get("budget", {}).get("maximum", 0) or 0),
            "budget_currency": (p.get("currency", {}) or {}).get("code") or "USD",
            "job_type": "fixed" if p.get("type") == "fixed" else "unknown",
            "bids_count": int(p.get("bid_stats", {}).get("bid_count", 0) or 0),
            "posted_at": now_utc(),
        })
    return out

async def pph_search(q: str) -> List[dict]:
    if not ENABLE_PPH:
        return []
    # απλό HTML search – κρατάμε το πλαίσιο, εσύ έχεις ήδη parsing
    url = f"https://www.peopleperhour.com/freelance-jobs?q={httpx.QueryParams({'q': q}).get('q')}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url)
        log.info("HTTP Request: GET %s %s", url, r.status_code)
        r.raise_for_status()
    # Αν έχεις ήδη parser, κάλεσε τον εδώ. Προσωρινά επιστρέφουμε empty -> δεν σπάει τίποτα.
    return []

async def kariera_search(q: str) -> List[dict]:
    if not ENABLE_KARIERA:
        return []
    url = f"https://www.kariera.gr/jobs?keyword={httpx.QueryParams({'keyword': q}).get('keyword')}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url)
        log.info("HTTP Request: GET %s %s", url, r.status_code)
        r.raise_for_status()
    # Έχεις ήδη post-filter στον κώδικά σου. Κράτα τον όπως είναι. Εδώ empty για ασφάλεια.
    return []

# ---------- Job matching (κρατά τη δική σου λογική) ----------
def match_job(text: str, keywords: List[str]) -> Optional[str]:
    t = (text or "").lower()
    for kw in keywords:
        kw = (kw or "").strip().lower()
        if not kw:
            continue
        if kw in t:
            return kw
    return None

# ---------- Upsert Job (σύμφωνα με το τρέχον schema: external_id NOT NULL) ----------
def upsert_job(db, j: dict) -> Job:
    # find by (source, external_id)
    existing = db.query(Job).filter(
        Job.source == j["source"],
        Job.external_id == j["external_id"],
    ).one_or_none()
    if existing:
        # light update
        existing.title = j.get("title", existing.title)
        existing.description = j.get("description", existing.description)
        existing.url = j.get("url", existing.url)
        existing.original_url = j.get("original_url", existing.original_url)
        existing.proposal_url = j.get("proposal_url", existing.proposal_url)
        existing.budget_min = j.get("budget_min", existing.budget_min)
        existing.budget_max = j.get("budget_max", existing.budget_max)
        existing.budget_currency = j.get("budget_currency", existing.budget_currency)
        existing.job_type = j.get("job_type", existing.job_type)
        existing.bids_count = j.get("bids_count", existing.bids_count)
        existing.updated_at = now_utc()
        return existing
    rec = Job(
        source=j["source"],
        external_id=j["external_id"],
        title=j.get("title", ""),
        description=j.get("description", ""),
        url=j.get("url"),
        original_url=j.get("original_url"),
        proposal_url=j.get("proposal_url"),
        budget_min=j.get("budget_min"),
        budget_max=j.get("budget_max"),
        budget_currency=j.get("budget_currency") or "USD",
        job_type=j.get("job_type"),
        bids_count=j.get("bids_count") or 0,
        matched_keyword=j.get("matched_keyword"),
        posted_at=j.get("posted_at") or now_utc(),
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    db.add(rec)
    return rec

# ---------- Compose Telegram card (όπως το έχεις) ----------
def job_card_text(job: Job) -> str:
    # budget + USD conversion
    usd_range = ""
    if job.budget_min is not None and job.budget_max is not None and job.budget_currency:
        usd_min, usd_max = usd_convert(job.budget_min, job.budget_currency), usd_convert(job.budget_max, job.budget_currency)
        if usd_min is not None and usd_max is not None:
            usd_range = f"\n~ ${usd_min:,.2f}–${usd_max:,.2f} USD"
    bids_line = f"\nBids: {job.bids_count}" if job.bids_count is not None else ""
    return (
        f"*{job.title}*\n\n"
        f"*Source:* Freelancer\n"
        f"*Type:* {job.job_type.capitalize() if job.job_type else '—'}\n"
        f"*Budget:* {int(job.budget_min) if job.budget_min else 0}–{int(job.budget_max) if job.budget_max else 0} {job.budget_currency or 'USD'}"
        f"{usd_range}"
        f"{bids_line}\n"
        f"*Posted:* recent\n\n"
        f"{(job.description or '')[:300]} …\n\n"
        f"_Matched:_ {job.matched_keyword or '—'}"
    )

def job_card_kb(job: Job) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "📦 Proposal", "url": job.proposal_url or job.original_url or job.url or ""},
                {"text": "🔗 Original", "url": job.original_url or job.url or ""},
            ],
            [
                {"text": "⭐ Keep", "callback_data": f"keep:{job.id}"},
                {"text": "🗑️ Delete", "callback_data": f"delete:{job.id}"},
            ]
        ]
    }

# ---------- Per-user processing ----------
async def process_user(db, u: User) -> Tuple[int, Dict[str, Dict[str, Optional[int]]]]:
    """
    Returns (sent_count, feeds_totals_dict)
    feeds_totals_dict format:
    {
      "freelancer": {"count": int, "error": Optional[str]},
      "pph": {"count": int, "error": Optional[str]},
      ...
    }
    """
    sent = 0
    feeds_totals = {
        "freelancer": {"count": 0, "error": None},
        "pph": {"count": 0, "error": None},
        "kariera": {"count": 0, "error": None},
    }

    # force-load keywords now to avoid lazy-load after session close
    kws = [k.keyword for k in (u.keywords or [])]
    if not kws:
        return 0, feeds_totals

    async def handle_jobs(source_name: str, jobs: List[dict]):
        nonlocal sent
        feeds_totals[source_name]["count"] += len(jobs)
        for jd in jobs:
            # match on title+desc
            matched = match_job((jd.get("title","") + " " + jd.get("description","")), kws)
            if not matched:
                continue
            jd["matched_keyword"] = matched
            job = upsert_job(db, jd)
            db.flush()
            # already sent?
            already = db.query(JobSent).filter(
                JobSent.user_id == u.id,
                JobSent.job_id == job.id
            ).one_or_none()
            if already:
                continue
            # send
            try:
                await tg_send(int(u.telegram_id), job_card_text(job), reply_markup=job_card_kb(job))
                db.add(JobSent(user_id=u.id, job_id=job.id, created_at=now_utc()))
                sent += 1
            except Exception as e:
                log.exception("send error: %s", e)

    # FREELANCER
    try:
        if ENABLE_FREELANCER:
            for kw in kws:
                jobs = await freelancer_search(kw)
                await handle_jobs("freelancer", jobs)
    except Exception as e:
        feeds_totals["freelancer"]["error"] = str(e)

    # PPH
    try:
        if ENABLE_PPH:
            for kw in kws:
                jobs = await pph_search(kw)
                await handle_jobs("pph", jobs)
    except Exception as e:
        feeds_totals["pph"]["error"] = str(e)

    # KARIERA
    try:
        if ENABLE_KARIERA:
            for kw in kws:
                jobs = await kariera_search(kw)
                await handle_jobs("kariera", jobs)
    except Exception as e:
        feeds_totals["kariera"]["error"] = str(e)

    return sent, feeds_totals

# ---------- Worker main loop ----------
async def worker_loop():
    log.info("Worker loop every %ss", WORKER_INTERVAL_SEC)
    while True:
        cycle_start = now_utc()
        sent_this_cycle = 0
        feeds_totals_accum: Dict[str, Dict[str, Optional[int]]] = {}

        try:
            # Use proper context manager (fixes _GeneratorContextManager errors)
            with get_session() as db:
                users: List[User] = db.query(User).all()
                for u in users:
                    try:
                        s, feeds_tot = await process_user(db, u)
                        sent_this_cycle += s
                        # merge totals across users
                        for name, d in feeds_tot.items():
                            if name not in feeds_totals_accum:
                                feeds_totals_accum[name] = {"count": 0, "error": None}
                            feeds_totals_accum[name]["count"] += d.get("count") or 0
                            # keep first error if any
                            if d.get("error") and not feeds_totals_accum[name]["error"]:
                                feeds_totals_accum[name]["error"] = d.get("error")
                        db.commit()
                    except Exception as e:
                        db.rollback()
                        log.exception("process_user error: %s", e)
        except Exception as e:
            log.exception("Worker loop DB error: %s", e)

        # ---- publish stats (NEW) ----
        cycle_seconds = (now_utc() - cycle_start).total_seconds()
        try:
            publish_stats(
                feeds_counts=feeds_totals_accum or {},
                cycle_seconds=cycle_seconds,
                sent_this_cycle=sent_this_cycle,
            )
        except Exception as e:
            log.exception("publish_stats failed: %s", e)
        # -----------------------------

        log.info("Worker cycle complete. Sent %s messages.", sent_this_cycle)
        await asyncio.sleep(WORKER_INTERVAL_SEC)

if __name__ == "__main__":
    asyncio.run(worker_loop())
