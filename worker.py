# worker.py
# -----------------------------------------------------------------------------
# Job fetcher/dispatcher loop
# -----------------------------------------------------------------------------

import asyncio
import os
import math
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from db_async import get_session, get_session_sync  # <— ΧΡΗΣΗ ADAPTER
from db import User, Keyword, Job, JobSent, SavedJob, now_utc  # ΜΟΝΤΕΛΑ / βοηθητικά
from worker_stats_sidecar import publish_stats  # για /feedsstatus

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# --------------- helpers ----------------

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

def md_esc(s: str) -> str:
    return s.replace("_", r"\_").replace("*", r"\*").replace("[", r"\[").replace("`", r"\`")

# --------------- FEEDS (μείνανε ως είχαν) ----------------
# Δείχνω μόνο freelancer/pph/kariera σαν παράδειγμα· άφησα hooks για τα υπόλοιπα.

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
    out = []
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

async def fetch_pph(q: str) -> List[dict]:
    url = f"https://www.peopleperhour.com/freelance-jobs?q={q}"
    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.get(url)
        r.raise_for_status()
    # placeholder parser (κρατάμε μόνο link τίτλο)
    return []

async def fetch_kariera(q: str) -> List[dict]:
    url = f"https://www.kariera.gr/jobs?keyword={q}"
    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.get(url)
        r.raise_for_status()
    # placeholder parser (post-filter γίνεται αλλού)
    return []

# ---------------- persist / send ----------------

async def upsert_and_send(db, u: User, job_payloads: List[dict]) -> int:
    sent = 0
    for payload in job_payloads:
        # upsert με external_id + source
        j = db.query(Job).filter(
            Job.source == payload["source"],
            Job.external_id == payload["external_id"]
        ).one_or_none()
        if not j:
            j = Job(**payload)
            db.add(j)
            db.commit()
            db.refresh(j)

        # μην το στείλουμε 2 φορές στον ίδιο χρήστη
        already = db.query(JobSent).filter(
            JobSent.user_id == u.id,
            JobSent.job_id == j.id
        ).one_or_none()
        if already:
            continue

        # κάρτα
        title = md_esc(j.title or "Untitled")
        lines = [
            f"*{title}*",
            f"Source: Freelancer" if j.source == "freelancer" else f"Source: {j.source.title()}",
        ]
        if j.job_type:
            lines.append(f"Type: {j.job_type.title()}")
        if j.budget_min or j.budget_max:
            rng = f"{int(j.budget_min) if j.budget_min else ''}–{int(j.budget_max) if j.budget_max else ''} {j.budget_currency or ''}".strip("– ").strip()
            lines.append(f"Budget: {rng}")
        if j.bids_count:
            lines.append(f"Bids: {j.bids_count}")
        lines.append("Posted: recent")
        lines.append("")
        desc = (j.description or "")[:600]
        if desc:
            lines.append(desc + (" …" if len(j.description or "") > 600 else ""))
        lines.append("")
        lines.append(f"Matched: {md_esc(j.matched_keyword or '')}")

        text = "\n".join(lines)

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

# ---------------- main per-user ----------------

async def process_user(u: User) -> int:
    sent = 0
    async with get_session() as db:  # <— ΤΩΡΑ είναι νόμιμο
        # φορτώνουμε μαζί και keywords (avoid lazy-load problems)
        user = db.query(User).options(joinedload(User.keywords)).filter(User.id == u.id).one()
        kws = [k.keyword for k in (user.keywords or [])]
        if not kws:
            return 0

        feeds_counts: Dict[str, Dict[str, Any]] = {}
        for kw in kws:
            # FREELANCER
            fl = await fetch_freelancer(kw)
            feeds_counts.setdefault("freelancer", {"count": 0, "error": None})
            feeds_counts["freelancer"]["count"] += len(fl)
            sent += await upsert_and_send(db, user, fl)

            # PPH (placeholder)
            try:
                pph = await fetch_pph(kw)
                feeds_counts.setdefault("pph", {"count": 0, "error": None})
                feeds_counts["pph"]["count"] += len(pph)
                # sent += await upsert_and_send(db, user, pph)
            except Exception as e:
                feeds_counts.setdefault("pph", {"count": 0, "error": str(e)})

            # KARIERA (placeholder)
            try:
                kr = await fetch_kariera(kw)
                feeds_counts.setdefault("kariera", {"count": 0, "error": None})
                feeds_counts["kariera"]["count"] += len(kr)
                # sent += await upsert_and_send(db, user, kr)
            except Exception as e:
                feeds_counts.setdefault("kariera", {"count": 0, "error": str(e)})

        # δημοσίευση μετρικών για /feedsstatus
        publish_stats(
            feeds_counts=feeds_counts,
            cycle_seconds=0.0,  # αν μετράς διάρκεια βάλε εδώ
            sent_this_cycle=sent,
        )
    return sent

# ---------------- loop ----------------

async def worker_loop():
    while True:
        total = 0
        try:
            # παίρνουμε τους ενεργούς χρήστες
            async with get_session() as db:
                users = db.query(User).filter(User.is_blocked == False).all()
            for u in users:
                total += await process_user(u)
        except Exception as e:
            # απλή προστασία – να μην πέφτει ο loop
            print(f"[worker] loop error: {e}")
        finally:
            print(f"[worker] cycle done. sent={total}")
        await asyncio.sleep(int(os.getenv("WORKER_INTERVAL", "120")))

if __name__ == "__main__":
    asyncio.run(worker_loop())
