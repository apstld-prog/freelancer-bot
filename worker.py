# worker.py
# -----------------------------------------------------------------------------
# Sync DB sessions (SessionLocal), async HTTP/Telegram. Κανένα "async with get_session()".
# -----------------------------------------------------------------------------

import asyncio
import os
from typing import List, Dict, Any, Optional

import httpx

from db import SessionLocal, User, Keyword, Job, JobSent, SavedJob, now_utc
# publish_stats είναι optional – αν λείπει το module, απλά no-op
try:
    from worker_stats_sidecar import publish_stats  # pragma: no cover
except Exception:  # pragma: no cover
    def publish_stats(**kwargs):
        pass

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "120"))


def md_esc(s: str) -> str:
    return (
        s.replace("_", r"\_")
        .replace("*", r"\*")
        .replace("[", r"\[")
        .replace("`", r"\`")
    )

async def tg_send(chat_id: int, text: str, reply_markup: Optional[dict] = None, parse_mode: Optional[str] = None):
    async with httpx.AsyncClient(timeout=20) as client:
        payload = {"chat_id": chat_id, "text": text}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        if parse_mode:
            payload["parse_mode"] = parse_mode
        r = await client.post(f"{API_URL}/sendMessage", json=payload)
        r.raise_for_status()
        return r.json()


# ----------------- FREELANCER FEED -----------------

async def fetch_freelancer(q: str) -> List[dict]:
    url = "https://www.freelancer.com/api/projects/0.1/projects/active/"
    params = {
        "query": q,
        "limit": 30,
        "compact": "true",
        "user_details": "true",
        "job_details": "true",
        "full_description": "true",
    }
    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()

    projects = data.get("result", {}).get("projects", []) or []
    out: List[dict] = []
    for p in projects:
        out.append({
            "source": "freelancer",
            "external_id": str(p.get("id")),
            "title": p.get("title") or "",
            "description": (p.get("description") or "")[:2000],
            "url": f"https://www.freelancer.com/projects/{p.get('id')}",
            "proposal_url": None,
            "original_url": f"https://www.freelancer.com/projects/{p.get('id')}",
            "budget_min": float(p.get("budget", {}).get("minimum", 0) or 0),
            "budget_max": float(p.get("budget", {}).get("maximum", 0) or 0),
            "budget_currency": p.get("currency", {}).get("code") or "USD",
            "job_type": "fixed" if (p.get("type") == "fixed") else "hourly",
            "bids_count": int(p.get("bid_stats", {}).get("bid_count", 0) or 0),
            "matched_keyword": q,
            "posted_at": now_utc(),
        })
    return out


# ----------------- persist/send -----------------

async def upsert_and_send(db, u: User, job_payloads: List[dict]) -> int:
    sent = 0
    for payload in job_payloads:
        j = db.query(Job).filter(
            Job.source == payload["source"],
            Job.external_id == payload["external_id"]
        ).one_or_none()
        if not j:
            j = Job(**payload)
            db.add(j)
            db.commit()
            db.refresh(j)

        already = db.query(JobSent).filter(
            JobSent.user_id == u.id,
            JobSent.job_id == j.id
        ).one_or_none()
        if already:
            continue

        title = md_esc(j.title or "Untitled")
        lines = [
            f"*{title}*",
            f"Source: {'Freelancer' if j.source=='freelancer' else j.source.title()}",
            f"Type: {j.job_type.title()}" if j.job_type else None,
        ]
        if j.budget_min or j.budget_max:
            rng = f"{int(j.budget_min) if j.budget_min else ''}–{int(j.budget_max) if j.budget_max else ''} {j.budget_currency or ''}"
            lines.append(f"Budget: {rng.strip('– ').strip()}")
        if j.bids_count:
            lines.append(f"Bids: {j.bids_count}")
        lines.append("Posted: recent")
        lines.append("")
        desc = (j.description or "")[:600]
        if desc:
            lines.append(desc + (" …" if len(j.description or "") > 600 else ""))
        lines.append("")
        if j.matched_keyword:
            lines.append(f"Keyword matched: {md_esc(j.matched_keyword)}")
        text = "\n".join([x for x in lines if x is not None])

        kb = {
            "inline_keyboard": [
                [
                    {"text": "📦 Proposal", "url": j.proposal_url or j.url},
                    {"text": "🔗 Original", "url": j.original_url or j.url},
                ],
                [
                    {"text": "⭐ Keep", "callback_data": f"keep:{j.id}"},
                    {"text": "🗑️ Delete", "callback_data": f"del:{j.id}"},
                ],
            ]
        }
        await tg_send(int(u.telegram_id), text, reply_markup=kb, parse_mode="Markdown")

        db.add(JobSent(user_id=u.id, job_id=j.id))
        db.commit()
        sent += 1
    return sent


# ----------------- per-user -----------------

async def process_user(u: User) -> int:
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.id == u.id).one()
        kws = [k.keyword for k in (u.keywords or [])]
        if not kws:
            return 0

        sent_total = 0
        feeds_counts: Dict[str, Dict[str, Any]] = {}

        for kw in kws:
            fl = await fetch_freelancer(kw)
            feeds_counts.setdefault("freelancer", {"count": 0, "error": None})
            feeds_counts["freelancer"]["count"] += len(fl)
            sent_total += await upsert_and_send(db, u, fl)

        publish_stats(
            feeds_counts=feeds_counts,
            cycle_seconds=0.0,
            sent_this_cycle=sent_total,
        )
        return sent_total
    finally:
        try:
            db.close()
        except Exception:
            pass


# ----------------- loop -----------------

async def worker_loop():
    while True:
        total = 0
        try:
            db = SessionLocal()
            try:
                users = db.query(User).filter(User.is_blocked == False).all()
            finally:
                db.close()

            for u in users:
                total += await process_user(u)

        except Exception as e:
            print(f"ERROR: worker loop error: {e}")
        finally:
            print(f"INFO: Worker cycle complete. Sent {total} messages.")
        await asyncio.sleep(WORKER_INTERVAL)


if __name__ == "__main__":
    asyncio.run(worker_loop())
