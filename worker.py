# worker.py
# -----------------------------------------------------------------------------
# Worker που διαβάζει keywords, φέρνει αγγελίες (Freelancer) και τις στέλνει
# σε Telegram, με σωστό conversion σε USD.
# -----------------------------------------------------------------------------
import asyncio
import os
import time
from typing import List, Dict, Any, Optional

import httpx
from db import SessionLocal, User, Keyword, Job, JobSent, SavedJob, now_utc

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "120"))

# ---------------- Exchange rates (cache 1h) ----------------
_rates_cache: Dict[str, Any] = {"ts": 0.0, "rates": {"USD": 1.0}}

async def get_rates() -> Dict[str, float]:
    """Return dict like {'USD':1, 'EUR':0.92, ...} base=USD. Cached 1h."""
    now = time.time()
    if now - _rates_cache["ts"] < 3600 and _rates_cache.get("rates"):
        return _rates_cache["rates"]  # cached
    url = "https://api.exchangerate.host/latest?base=USD"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
            rates = data.get("rates") or {}
            rates["USD"] = 1.0
            _rates_cache["rates"] = rates
            _rates_cache["ts"] = now
            return rates
    except Exception as e:
        print(f"Exchange rate fetch failed: {e}")
        return _rates_cache.get("rates", {"USD": 1.0})

def md_esc(s: str) -> str:
    """Ασφαλής escaping για markdown text."""
    return (
        s.replace("_", r"\_")
        .replace("*", r"\*")
        .replace("[", r"\[")
        .replace("`", r"\`")
    )

async def tg_send(chat_id: int, text: str, reply_markup: Optional[dict] = None, parse_mode: Optional[str] = None):
    """Αποστολή μηνύματος στο Telegram."""
    async with httpx.AsyncClient(timeout=20) as client:
        payload = {"chat_id": chat_id, "text": text}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        if parse_mode:
            payload["parse_mode"] = parse_mode
        r = await client.post(f"{API_URL}/sendMessage", json=payload)
        r.raise_for_status()
        return r.json()

# ---------------- Freelancer feed ----------------
async def fetch_freelancer(q: str) -> List[dict]:
    """Αναζήτηση στο Freelancer API."""
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
            "budget_currency": (p.get("currency", {}) or {}).get("code") or "USD",
            "job_type": "fixed" if (p.get("type") == "fixed") else "hourly",
            "bids_count": int((p.get("bid_stats", {}) or {}).get("bid_count", 0) or 0),
            "matched_keyword": q,
            "posted_at": now_utc(),
        })
    return out

# ---------------- render card ----------------
async def format_job_text(j: Job) -> str:
    """Μορφοποίηση του κειμένου που στέλνεται στο Telegram."""
    title = md_esc(j.title or "Untitled")

    lines = [
        f"*{title}*",
        f"Source: {'Freelancer' if j.source == 'freelancer' else j.source.title()}",
        f"Type: {j.job_type.title()}" if j.job_type else None,
    ]

    # Native currency budget
    native_budget_line = None
    if (j.budget_min or j.budget_max) and j.budget_currency:
        mn = int(j.budget_min) if j.budget_min else None
        mx = int(j.budget_max) if j.budget_max else None
        if mn and mx:
            native_budget_line = f"{mn}–{mx} {j.budget_currency}"
        elif mn:
            native_budget_line = f"{mn}+ {j.budget_currency}"
        elif mx:
            native_budget_line = f"up to {mx} {j.budget_currency}"
    if native_budget_line:
        lines.append(f"Budget: {native_budget_line}")

    # USD conversion
    try:
        if j.budget_currency and j.budget_currency.upper() != "USD" and (j.budget_min or j.budget_max):
            rates = await get_rates()
            rate = float(rates.get(j.budget_currency.upper(), 0))
            if rate > 0:
                mn_usd = (j.budget_min or 0) / rate
                mx_usd = (j.budget_max or 0) / rate
                if mn_usd or mx_usd:
                    if mn_usd and mx_usd:
                        usd_line = f"~ ${mn_usd:,.2f}–${mx_usd:,.2f} USD"
                    elif mn_usd:
                        usd_line = f"~ from ${mn_usd:,.2f} USD"
                    else:
                        usd_line = f"~ up to ${mx_usd:,.2f} USD"
                    lines.append(usd_line)
    except Exception as e:
        print(f"USD conversion failed: {e}")

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

    return "\n".join([x for x in lines if x is not None])

# ---------------- store & send ----------------
async def upsert_and_send(db, u: User, job_payloads: List[dict]) -> int:
    """Εισαγωγή/ενημέρωση job και αποστολή στον χρήστη."""
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

        text = await format_job_text(j)
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

# ---------------- user cycle ----------------
async def process_user(u: User) -> int:
    """Επεξεργάζεται τα keywords του κάθε user."""
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.id == u.id).one()
        kws = [k.keyword for k in (u.keywords or [])]
        if not kws:
            return 0

        total = 0
        for kw in kws:
            fl = await fetch_freelancer(kw)
            total += await upsert_and_send(db, u, fl)
        return total
    finally:
        try:
            db.close()
        except Exception:
            pass

# ---------------- main loop ----------------
async def worker_loop():
    """Κεντρικός loop για όλα τα accounts."""
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
            print(f"Worker error: {e}")
        finally:
            print(f"INFO: Worker cycle complete. Sent {total} messages.")
        await asyncio.sleep(WORKER_INTERVAL)

if __name__ == "__main__":
    asyncio.run(worker_loop())
