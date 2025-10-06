import asyncio
import logging
import os
from typing import Dict, Any, List

import httpx

from db import get_session, now_utc, User, Job, JobSent
from worker_stats_sidecar import publish_stats  # για feeds status

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("db")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# --------------------------
# TG send
# --------------------------
async def tg_send(chat_id: int, text: str, *, reply_markup=None, parse_mode: str = "HTML"):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{TG_API}/sendMessage", json=payload)
        r.raise_for_status()
        log.info("HTTP Request: POST %s/sendMessage OK", TG_API)
        return r.json()

# --------------------------
# Job card helpers (ίδιο layout με bot)
# --------------------------
def html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def format_job_card(job: Job) -> str:
    budget = ""
    if job.budget_min is not None and job.budget_max is not None and job.budget_currency:
        budget = f"{int(job.budget_min)}–{int(job.budget_max)} {job.budget_currency}"
    bids = str(job.bids_count) if job.bids_count is not None else "—"
    desc = html_escape((job.description or "").strip())
    if len(desc) > 280:
        desc = desc[:277] + " …"
    return (
        f"<b>{html_escape(job.title or '(no title)')}</b>\n\n"
        f"<b>Source:</b> {html_escape(job.source.capitalize())}\n"
        f"<b>Type:</b> {html_escape(job.job_type or '—')}\n"
        f"<b>Budget:</b> {budget or '—'}\n"
        f"<b>Bids:</b> {bids}\n"
        f"<b>Posted:</b> recent\n\n"
        f"{desc}\n\n"
        f"<i>Matched:</i> {html_escape(job.matched_keyword or '')}"
    )

def job_keyboard(job: Job) -> Dict[str, Any]:
    jid = f"{job.source}-{job.source_id}"
    return {
        "inline_keyboard": [
            [
                {"text": "📦 Proposal", "url": job.proposal_url or job.url},
                {"text": "🔗 Original", "url": job.original_url or job.url},
            ],
            [
                {"text": "⭐ Keep", "callback_data": f"job:keep:{jid}"},
                {"text": "🗑️ Delete", "callback_data": f"job:delmsg:{jid}"},
            ],
        ]
    }

# --------------------------
# Feeds (placeholder: μόνο Freelancer ήδη έτοιμο στο σύστημά σου)
# --------------------------
async def fetch_freelancer_for_keyword(client: httpx.AsyncClient, kw: str) -> List[dict]:
    url = "https://www.freelancer.com/api/projects/0.1/projects/active/"
    params = {
        "query": kw,
        "limit": 30,
        "compact": "true",
        "user_details": "true",
        "job_details": "true",
        "full_description": "true",
    }
    r = await client.get(url, params=params)
    r.raise_for_status()
    data = r.json()
    items = data.get("result", {}).get("projects", []) or []
    out = []
    for p in items:
        out.append({
            "source": "freelancer",
            "source_id": str(p.get("id")),
            "title": p.get("title") or "",
            "description": p.get("description") or "",
            "url": f"https://www.freelancer.com/projects/{p.get('id')}",
            "original_url": f"https://www.freelancer.com/projects/{p.get('id')}",
            "proposal_url": f"https://www.freelancer.com/projects/{p.get('id')}",
            "budget_min": float((p.get("budget", {}) or {}).get("minimum", 0)) if p.get("budget") else None,
            "budget_max": float((p.get("budget", {}) or {}).get("maximum", 0)) if p.get("budget") else None,
            "budget_currency": (p.get("currency", {}) or {}).get("code") if p.get("currency") else None,
            "job_type": "fixed" if (p.get("type") == "fixed") else "hourly",
            "bids_count": p.get("bid_stats", {}).get("bid_count") if p.get("bid_stats") else None,
            "matched_keyword": kw,
        })
    return out

# --------------------------
# Worker main
# --------------------------
async def process_user(u: User) -> int:
    sent = 0
    async with httpx.AsyncClient(timeout=25) as client:
        # keywords
        kws = [k.keyword for k in (u.keywords or [])]
        all_cards: List[dict] = []
        for kw in kws:
            try:
                jobs = await fetch_freelancer_for_keyword(client, kw)
                # persist & prepare cards
                for j in jobs:
                    # store or fetch local
                    async with get_session() as dbs:
                        existing = dbs.query(Job).filter(
                            Job.source == j["source"],
                            Job.source_id == j["source_id"]
                        ).one_or_none()
                        if not existing:
                            job = Job(
                                source=j["source"],
                                source_id=j["source_id"],
                                title=j["title"],
                                description=j["description"],
                                url=j["url"],
                                original_url=j["original_url"],
                                proposal_url=j["proposal_url"],
                                budget_min=j["budget_min"],
                                budget_max=j["budget_max"],
                                budget_currency=j["budget_currency"],
                                job_type=j["job_type"],
                                bids_count=j["bids_count"],
                                matched_keyword=j["matched_keyword"],
                                posted_at=now_utc(),
                                created_at=now_utc(),
                                updated_at=now_utc(),
                            )
                            dbs.add(job)
                            dbs.commit()
                            dbs.refresh(job)
                        else:
                            job = existing
                    # check sent
                    async with get_session() as dbs2:
                        already = dbs2.query(JobSent).filter(JobSent.user_id == u.id, JobSent.job_id == job.id).one_or_none()
                        if already:
                            continue
                        text = format_job_card(job)
                        kb = job_keyboard(job)
                        try:
                            await tg_send(int(u.telegram_id), text, reply_markup=kb, parse_mode="HTML")
                            dbs2.add(JobSent(user_id=u.id, job_id=job.id, created_at=now_utc()))
                            dbs2.commit()
                            sent += 1
                        except Exception as e:
                            log.warning("Send failed: %s", e)
            except Exception as e:
                log.warning("fetch/send error for kw %s: %s", kw, e)
    return sent

async def worker_loop():
    log.info("Worker loop starting…")
    while True:
        cycle_start = now_utc()
        feeds_counts = {"freelancer": {"count": 0, "error": None}}
        total_sent = 0
        try:
            async with get_session() as db:
                users = db.query(User).filter(User.is_blocked == False).all()
            for u in users:
                try:
                    s = await process_user(u)
                    total_sent += s
                    feeds_counts["freelancer"]["count"] += s
                except Exception as e:
                    log.exception("process_user error: %s", e)
        except Exception as e:
            log.exception("Loop-level error: %s", e)

        cycle_seconds = (now_utc() - cycle_start).total_seconds()
        try:
            publish_stats(feeds_counts=feeds_counts, cycle_seconds=cycle_seconds, sent_this_cycle=total_sent)
        except Exception as e:
            log.warning("publish_stats failed: %s", e)

        log.info("Worker cycle complete. Sent %d messages.", total_sent)
        await asyncio.sleep(int(os.getenv("WORKER_INTERVAL", "300")))

if __name__ == "__main__":
    asyncio.run(worker_loop())
