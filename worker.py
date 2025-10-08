# worker.py
# -*- coding: utf-8 -*-
# ==========================================================
# UI_LOCKED: Message layout & buttons must match bot.py
# ==========================================================
import os, asyncio, logging, html, re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import httpx
from sqlalchemy.exc import SQLAlchemyError

from db import (
    SessionLocal, User, Keyword, Job, JobSent
)
try:
    from db import ensure_schema as _ensure_schema
except Exception:
    _ensure_schema = None

UTC = timezone.utc
log = logging.getLogger("worker")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

BOT_TOKEN             = os.getenv("BOT_TOKEN", "").strip()
AFFILIATE_PREFIX      = os.getenv("AFFILIATE_PREFIX", "").strip()
CYCLE_SECONDS         = int(os.getenv("WORKER_INTERVAL", "60"))
FREELANCER_LIMIT      = 30
SKYWALKER_FEED_URL    = os.getenv("SKYWALKER_FEED", "https://www.skywalker.gr/jobs/feed")
SEND_TIMEOUT_SECONDS  = 15

FX: Dict[str, float] = {
    "USD": 1.0, "EUR": 1.09, "GBP": 1.27, "AUD": 0.65, "CAD": 0.73,
    "TRY": 0.03, "INR": 0.012,
}

def now_utc() -> datetime:
    return datetime.now(UTC)

def tg_api(url: str) -> str:
    return f"https://api.telegram.org/bot{BOT_TOKEN}/{url}"

def safe_rate(ccy: Optional[str]) -> float:
    return FX.get((ccy or "").upper(), 0.0)

def usd_range(lo: Optional[float], hi: Optional[float], ccy: Optional[str]) -> Optional[Tuple[float, float]]:
    r = safe_rate(ccy)
    if r <= 0:
        return None
    lo_usd = (lo if lo is not None else hi or 0.0) * r
    hi_usd = (hi if hi is not None else lo or 0.0) * r
    return (lo_usd, hi_usd)

def pretty_usd(lo: float, hi: float) -> str:
    if lo and hi:
        return f"${lo:,.0f}–${hi:,.0f}"
    v = lo or hi
    return f"${v:,.0f}" if v else ""

def timeago(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    sec = max(0, int((now_utc() - dt).total_seconds()))
    if sec < 60:
        return f"{sec}s ago"
    m = sec // 60
    if m < 60:
        return f"{m}m ago"
    h = m // 60
    if h < 24:
        return f"{h}h ago"
    d = h // 24
    return f"{d}d ago"

def affiliate(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    if not AFFILIATE_PREFIX:
        return url
    if url.startswith(AFFILIATE_PREFIX):
        return url
    return f"{AFFILIATE_PREFIX}{url}"

def norm_text(x: str) -> str:
    x = html.unescape(x or "")
    x = re.sub(r"\s+", " ", x).strip()
    return x

def ensure_job(db, source: str, source_id: str, **fields) -> Job:
    j = db.query(Job).filter(Job.source == source, Job.source_id == str(source_id)).one_or_none()
    if not j:
        j = Job(source=source, source_id=str(source_id), created_at=now_utc())
        db.add(j)
    for k, v in fields.items():
        setattr(j, k, v)
    j.updated_at = now_utc()
    db.commit(); db.refresh(j)
    return j

def already_sent(db, user_id: int, job_id: int) -> bool:
    return db.query(JobSent).filter(JobSent.user_id == user_id, JobSent.job_id == job_id).one_or_none() is not None

def mark_sent(db, user_id: int, job_id: int):
    try:
        db.add(JobSent(user_id=user_id, job_id=job_id, created_at=now_utc()))
        db.commit()
    except Exception:
        db.rollback()

def user_keywords(db, u: User) -> List[str]:
    rows = db.query(Keyword.term).filter(Keyword.user_id == u.id).all()
    return [r[0] for r in rows if r and r[0]]

def user_active(u: User) -> bool:
    if getattr(u, "is_blocked", False):
        return False
    lic = getattr(u, "license_until", None)
    tri = getattr(u, "trial_end", None)
    exp = lic or tri
    return bool(exp and exp >= now_utc())

# ---- Fetchers -----------------------------------------------------

async def fetch_freelancer_for_keyword(client: httpx.AsyncClient, kw: str) -> List[dict]:
    url = (
        "https://www.freelancer.com/api/projects/0.1/projects/active/"
        f"?limit={FREELANCER_LIMIT}&compact=true&user_details=true&job_details=true&full_description=true"
        f"&query={kw}"
    )
    r = await client.get(url, timeout=SEND_TIMEOUT_SECONDS)
    r.raise_for_status()
    data = r.json()
    projects = (data.get("result") or {}).get("projects") or []
    out = []
    for p in projects:
        pid = p.get("id")
        if not pid:
            continue
        title = norm_text(p.get("title") or "")
        if not title:
            continue
        descr = norm_text((p.get("preview_description") or p.get("description") or "")[:3000])
        link = f"https://www.freelancer.com/projects/{pid}"
        b = p.get("budget") or {}
        curr = (b.get("currency") or {}).get("code")
        mn, mx = b.get("minimum"), b.get("maximum")
        posted = p.get("publish_time") or p.get("time_submitted")
        posted_dt = None
        try:
            if posted:
                posted_dt = datetime.fromisoformat(str(posted).replace("Z", "+00:00")).astimezone(UTC)
        except Exception:
            posted_dt = None
        out.append({
            "source": "Freelancer",
            "source_id": str(pid),
            "title": title,
            "description": descr,
            "url": link,
            "proposal_url": affiliate(link),
            "original_url": affiliate(link),
            "budget_min": float(mn) if mn is not None else None,
            "budget_max": float(mx) if mx is not None else None,
            "budget_currency": curr,
            "matched_keyword": kw,
            "posted_at": posted_dt,
        })
    return out

async def fetch_skywalker(client: httpx.AsyncClient) -> List[dict]:
    out = []
    try:
        r = await client.get(SKYWALKER_FEED_URL, timeout=SEND_TIMEOUT_SECONDS)
        r.raise_for_status()
        text = r.text
        items = re.split(r"</item>", text, flags=re.I)
        for raw in items:
            if "<item>" not in raw.lower():
                continue
            def gx(tag):
                m = re.search(fr"<{tag}>(.*?)</{tag}>", raw, flags=re.I | re.S)
                return norm_text(html.unescape(m.group(1))) if m else ""
            title, link, descr = gx("title"), gx("link"), gx("description")
            if not title:
                continue
            out.append({
                "source": "Skywalker",
                "source_id": link or title[:100],
                "title": title,
                "description": descr[:3000],
                "url": link,
                "proposal_url": affiliate(link),
                "original_url": affiliate(link),
                "posted_at": now_utc(),
            })
    except Exception as e:
        log.warning("Skywalker fetch failed: %s", e)
    return out

# ---- Senders ------------------------------------------------------

def compose_message(job: Job) -> str:
    parts = [html.escape(job.title or "Untitled")]
    if job.budget_min or job.budget_max:
        parts.append(f"🧾 Budget: {job.budget_min or ''}–{job.budget_max or ''} {job.budget_currency or ''}")
    parts.append(f"📎 Source: {html.escape(job.source or '')}")
    if getattr(job, "matched_keyword", None):
        parts.append(f"🔍 Match: <b><u>{html.escape(job.matched_keyword)}</u></b>")
    desc = html.escape((job.description or "").strip())[:1500]
    if desc:
        parts.append(f"📝 {desc}")
    when = job.posted_at
    if when:
        parts.append(f"⏱️ {timeago(when)}")
    return "\n".join(parts)

def compose_keyboard(job: Job):
    return {
        "inline_keyboard": [
            [
                {"text": "📨 Proposal", "url": job.proposal_url or job.url},
                {"text": "🔗 Original", "url": job.original_url or job.url},
            ],
            [
                {"text": "⭐ Save", "callback_data": f"job:save:{job.id}"},
                {"text": "🗑️ Delete", "callback_data": f"job:delete:{job.id}"},
            ],
        ]
    }

async def send_to_user(client: httpx.AsyncClient, u: User, job: Job) -> bool:
    chat_id = str(getattr(u, "telegram_id", None) or "")
    if not chat_id:
        return False
    payload = {
        "chat_id": chat_id,
        "text": compose_message(job),
        "reply_markup": compose_keyboard(job),
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = await client.post(tg_api("sendMessage"), json=payload, timeout=SEND_TIMEOUT_SECONDS)
        r.raise_for_status()
        return True
    except Exception as e:
        log.warning("send_to_user failed: %s", e)
        return False

# ---- Main cycle ---------------------------------------------------

async def cycle_once():
    db = SessionLocal()
    sent = 0
    try:
        users = db.query(User).all()
        if not users:
            log.info("No users in DB.")
            return
        async with httpx.AsyncClient(follow_redirects=True, timeout=SEND_TIMEOUT_SECONDS) as client:
            sky_jobs = await fetch_skywalker(client)
            for u in users:
                if not user_active(u):
                    continue
                kws = user_keywords(db, u)
                if not kws:
                    continue
                all_jobs = []
                for kw in kws:
                    try:
                        all_jobs += await fetch_freelancer_for_keyword(client, kw)
                    except Exception as e:
                        log.warning("Freelancer fetch failed (%s): %s", kw, e)
                pool = {f"{j['source']}-{j['source_id']}": j for j in sky_jobs + all_jobs}
                for rec in pool.values():
                    txt = (rec.get("title", "") + " " + rec.get("description", "")).lower()
                    if not any(k.lower() in txt for k in kws):
                        continue
                    try:
                        j = ensure_job(db, rec["source"], str(rec["source_id"]), **rec)
                    except SQLAlchemyError as e:
                        db.rollback()
                        log.warning("Job upsert failed: %s", e)
                        continue
                    if already_sent(db, u.id, j.id):
                        continue
                    if await send_to_user(client, u, j):
                        mark_sent(db, u.id, j.id)
                        sent += 1
        log.info("Worker cycle complete. Sent %d messages.", sent)
    finally:
        db.close()

async def run_forever():
    if _ensure_schema:
        _ensure_schema()
    log.info("Worker started. Cycle every %ss", CYCLE_SECONDS)
    while True:
        try:
            await cycle_once()
        except Exception as e:
            log.warning("Cycle error: %s", e)
        await asyncio.sleep(CYCLE_SECONDS)

if __name__ == "__main__":
    asyncio.run(run_forever())
