# worker.py
import os
import asyncio
import logging
from typing import Dict, List, Optional

import httpx
from sqlalchemy.orm import joinedload

from db import get_session, now_utc, User, Job  # το schema όπως το έχεις (Job έχει external_id)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("db")

BOT_TOKEN = os.environ["BOT_TOKEN"]
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ---------------- Telegram ----------------
async def tg_send(chat_id: int, text: str, reply_markup=None, parse_mode: Optional[str] = None) -> None:
    async with httpx.AsyncClient(timeout=30) as cli:
        payload = {"chat_id": chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = reply_markup
        r = await cli.post(f"{TG_API}/sendMessage", json=payload)
        r.raise_for_status()
        logging.info("HTTP Request: POST %s/sendMessage OK", TG_API)

# ---------------- Fetchers (δεν αλλάζω λογική) ----------------
async def fetch_freelancer(keyword: str) -> List[Dict]:
    url = "https://www.freelancer.com/api/projects/0.1/projects/active/"
    params = {
        "query": keyword,
        "limit": 30,
        "compact": "true",
        "user_details": "true",
        "job_details": "true",
        "full_description": "true",
    }
    async with httpx.AsyncClient(timeout=30) as cli:
        r = await cli.get(url, params=params)
        r.raise_for_status()
        data = r.json()

    jobs: List[Dict] = []
    for p in data.get("result", {}).get("projects", []):
        jobs.append({
            "source": "freelancer",
            "external_id": str(p.get("id")),
            "title": p.get("title") or "",
            "description": (p.get("description") or "")[:600],
            "url": f"https://www.freelancer.com/projects/{p.get('id')}",
            "original_url": f"https://www.freelancer.com/projects/{p.get('id')}",
            "proposal_url": None,
            "budget_min": float((p.get("budget") or {}).get("minimum") or 0),
            "budget_max": float((p.get("budget") or {}).get("maximum") or 0),
            "budget_currency": ((p.get("currency") or {}).get("code")) or "USD",
            "job_type": "fixed" if p.get("type") == "fixed" else "hourly",
            "bids_count": int((p.get("bid_stats") or {}).get("bid_count") or 0),
            "matched_keyword": keyword,
            "posted_at": now_utc(),
        })
    return jobs

# ---------------- DB helpers ----------------
def job_exists(db, source: str, external_id: str) -> bool:
    return db.query(Job).filter(Job.source == source, Job.external_id == external_id).one_or_none() is not None

def save_job(db, j: Dict) -> Job:
    job = Job(
        source=j["source"],
        external_id=j["external_id"],
        title=j["title"],
        description=j["description"],
        url=j["url"],
        proposal_url=j["proposal_url"],
        original_url=j["original_url"],
        budget_min=j["budget_min"],
        budget_max=j["budget_max"],
        budget_currency=j["budget_currency"],
        job_type=j["job_type"],
        bids_count=j["bids_count"],
        matched_keyword=j["matched_keyword"],
        posted_at=j["posted_at"],
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job

def render_job_md(j: Dict) -> str:
    budget_line = ""
    if j["budget_min"] or j["budget_max"]:
        budget_line = f"*Budget:* {int(j['budget_min'])}–{int(j['budget_max'])} {j['budget_currency']}\n"
    return (
        f"*{j['title']}*\n\n"
        f"*Source:* Freelancer\n"
        f"*Type:* {'Fixed' if j['job_type']=='fixed' else 'Hourly'}\n"
        f"{budget_line}"
        f"*Bids:* {j['bids_count']}\n"
        f"*Posted:* recent\n\n"
        f"{j['description']}\n\n"
        f"_Matched:_ {j['matched_keyword']}"
    )

# ---------------- Core per-user send ----------------
async def send_for_user(telegram_id: int, keywords: List[str]) -> int:
    sent = 0
    for kw in keywords:
        try:
            jobs = await fetch_freelancer(kw)
        except Exception as e:
            log.warning("Freelancer fetch error for '%s': %s", kw, e)
            continue
        if not jobs:
            continue

        # store & send μέσα στο ίδιο session
        with get_session() as db:
            for j in jobs[:2]:  # throttle
                if job_exists(db, j["source"], j["external_id"]):
                    continue
                _ = save_job(db, j)
                text = render_job_md(j)
                kb = {
                    "inline_keyboard": [
                        [{"text": "🧾 Proposal", "url": j["proposal_url"] or j["original_url"]}],
                        [{"text": "🔗 Original", "url": j["original_url"]}],
                    ]
                }
                await tg_send(int(telegram_id), text, reply_markup=kb, parse_mode="Markdown")
                sent += 1
    return sent

# ---------------- Worker loop ----------------
async def worker_loop() -> None:
    log.info("Worker loop starting…")
    interval = int(os.getenv("WORKER_INTERVAL", "300"))
    while True:
        cycle_sent = 0

        # Εδώ κάνουμε eager-load τα keywords για να ΜΗΝ γίνει lazy-load εκτός session
        with get_session() as db:
            users = (
                db.query(User)
                .options(joinedload(User.keywords))
                .filter(User.is_blocked == False)  # noqa
                .all()
            )
            # αντιγράφουμε ΤΑ ΑΠΑΡΑΙΤΗΤΑ σε απλά types
            todo = [(int(u.telegram_id), [k.keyword for k in (u.keywords or [])]) for u in users]

        # Τώρα δεν υπάρχει πρόσβαση σε ORM objects εκτός session
        for tg_id, kws in todo:
            try:
                cycle_sent += await send_for_user(tg_id, kws)
            except Exception as e:
                log.error("process_user error: %s", e)

        log.info("Worker cycle complete. Sent %s messages.", cycle_sent)
        await asyncio.sleep(interval)

if __name__ == "__main__":
    asyncio.run(worker_loop())
