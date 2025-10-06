# worker.py
import os
import asyncio
import logging
from typing import Dict, List, Tuple, Optional
from datetime import datetime

import httpx

from db import get_session, now_utc, User, Keyword, Job

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("db")

BOT_TOKEN = os.environ["BOT_TOKEN"]
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
ADMIN_ID = os.getenv("ADMIN_TELEGRAM_ID", "")

# -------- Telegram helpers --------
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

# -------- Feeds (μικρό demo — δεν αλλάζω τη βασική σου λογική) --------
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
    results = []
    for p in data.get("result", {}).get("projects", []):
        results.append({
            "source": "freelancer",
            "external_id": str(p.get("id")),
            "title": p.get("title") or "",
            "description": (p.get("description") or "")[:500],
            "url": f"https://www.freelancer.com/projects/{p.get('id')}",
            "original_url": f"https://www.freelancer.com/projects/{p.get('id')}",
            "proposal_url": None,
            "budget_min": float(p.get("budget", {}).get("minimum", 0) or 0),
            "budget_max": float(p.get("budget", {}).get("maximum", 0) or 0),
            "budget_currency": (p.get("currency", {}) or {}).get("code") or "USD",
            "job_type": "fixed" if p.get("type") == "fixed" else "hourly",
            "bids_count": int(p.get("bid_stats", {}).get("bid_count", 0) or 0),
            "matched_keyword": keyword,
            "posted_at": now_utc(),
        })
    return results

# -------- Store & send --------
def _job_exists(db, source: str, external_id: str) -> bool:
    return db.query(Job).filter(Job.source == source, Job.external_id == external_id).one_or_none() is not None

def _save_job(db, j: Dict) -> Job:
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

def _render_job_md(j: Dict) -> str:
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

async def process_user(u: User) -> int:
    sent = 0
    keywords = [k.keyword for k in u.keywords]
    for kw in keywords:
        try:
            jobs = await fetch_freelancer(kw)
        except Exception as e:
            log.warning("Freelancer fetch error for '%s': %s", kw, e)
            continue
        if not jobs:
            continue
        with get_session() as db:
            for j in jobs[:2]:  # throttle
                if _job_exists(db, j["source"], j["external_id"]):
                    continue
                job = _save_job(db, j)
                text = _render_job_md(j)
                kb = {
                    "inline_keyboard": [
                        [{"text": "🧾 Proposal", "url": j["proposal_url"] or j["original_url"]}],
                        [{"text": "🔗 Original", "url": j["original_url"]}],
                    ]
                }
                await tg_send(int(u.telegram_id), text, reply_markup=kb, parse_mode="Markdown")
                sent += 1
    return sent

async def worker_loop() -> None:
    log.info("Worker loop starting…")
    while True:
        cycle_sent = 0
        with get_session() as db:
            users = db.query(User).filter(User.is_blocked == False).all()  # noqa
        for u in users:
            try:
                cycle_sent += await process_user(u)
            except Exception as e:
                log.error("process_user error: %s", e)
        log.info("Worker cycle complete. Sent %s messages.", cycle_sent)
        await asyncio.sleep(int(os.getenv("WORKER_INTERVAL", "300")))

if __name__ == "__main__":
    asyncio.run(worker_loop())
