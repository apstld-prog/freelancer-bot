# worker.py
# -*- coding: utf-8 -*-
# ==========================================================
# ⚠️ UI_LOCKED: Message layout & buttons must match bot.py
# ==========================================================
import os, asyncio, logging, html, re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import httpx
from sqlalchemy.exc import SQLAlchemyError

from db import (
    SessionLocal, init_db,
    User, Keyword, Job, JobSent, JobAction
)

UTC = timezone.utc
log = logging.getLogger("worker")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

BOT_TOKEN              = os.getenv("BOT_TOKEN", "").strip()
AFFILIATE_PREFIX      = os.getenv("AFFILIATE_PREFIX", "").strip()
CYCLE_SECONDS         = int(os.getenv("WORKER_INTERVAL", "60"))
FREELANCER_LIMIT      = 30
SKYWALKER_FEED_URL    = os.getenv("SKYWALKER_FEED", "https://www.skywalker.gr/jobs/feed")
SEND_TIMEOUT_SECONDS  = 15

FX: Dict[str, float] = {
    "USD": 1.0, "EUR": 1.09, "GBP": 1.27, "AUD": 0.65, "CAD": 0.73,
    "TRY": 0.03, "INR": 0.012,
}

def now_utc() -> datetime: return datetime.now(UTC)
def tg_api(url: str) -> str: return f"https://api.telegram.org/bot{BOT_TOKEN}/{url}"

def safe_rate(ccy: Optional[str]) -> float:
    return FX.get((ccy or "").upper(), 0.0)

def usd_range(lo: Optional[float], hi: Optional[float], ccy: Optional[str]) -> Optional[Tuple[float,float]]:
    r=safe_rate(ccy)
    if r<=0: return None
    lo_usd = (lo or hi or 0.0)*r if lo or hi else 0.0
    hi_usd = (hi or lo or 0.0)*r if lo or hi else 0.0
    return (lo_usd, hi_usd)

def pretty_usd(lo: float, hi: float) -> str:
    if lo and hi: return f"(${lo:,.0f}–${hi:,.0f})"
    v = lo or hi
    return f"(${v:,.0f})" if v else ""

def timeago(dt: Optional[datetime]) -> str:
    if not dt: return ""
    sec = max(0, int((now_utc() - dt).total_seconds()))
    if sec < 60: return f"{sec}s ago"
    m = sec // 60
    if m < 60: return f"{m}m ago"
    h = m // 60
    if h < 24: return f"{h}h ago"
    d = h // 24
    return f"{d}d ago"

def affiliate(url: Optional[str]) -> Optional[str]:
    if not url: return None
    if not AFFILIATE_PREFIX: return url
    if url.startswith(AFFILIATE_PREFIX): return url
    return f"{AFFILIATE_PREFIX}{url}"

def norm_text(x: str) -> str:
    x = html.unescape(x or "")
    x = re.sub(r"\s+", " ", x).strip()
    return x

def ensure_job(db, source: str, source_id: str, *,
               title: str,
               description: str,
               url: Optional[str],
               proposal_url: Optional[str],
               original_url: Optional[str],
               budget_min: Optional[float],
               budget_max: Optional[float],
               budget_currency: Optional[str],
               job_type: Optional[str],
               bids_count: Optional[int],
               matched_keyword: Optional[str],
               posted_at: Optional[datetime]) -> Job:
    j = db.query(Job).filter(Job.source==source, Job.source_id=str(source_id)).one_or_none()
    if not j:
        j = Job(source=source, source_id=str(source_id), created_at=now_utc())
        db.add(j)
    j.title = title or "Untitled"
    j.description = description or ""
    j.url = url or original_url or proposal_url or ""
    j.proposal_url = proposal_url or ""
    j.original_url = original_url or url or ""
    j.budget_min = budget_min
    j.budget_max = budget_max
    j.budget_currency = budget_currency
    j.job_type = job_type
    j.bids_count = bids_count
    if matched_keyword: j.matched_keyword = matched_keyword
    j.posted_at = posted_at or j.posted_at
    j.updated_at = now_utc()
    db.commit(); db.refresh(j)
    return j

def already_sent(db, user_id: int, job_id: int) -> bool:
    return db.query(JobSent).filter(JobSent.user_id==user_id, JobSent.job_id==job_id).one_or_none() is not None

def mark_sent(db, user_id: int, job_id: int):
    try:
        db.add(JobSent(user_id=user_id, job_id=job_id, created_at=now_utc()))
        db.commit()
    except Exception:
        db.rollback()

def user_keywords(db, u: User) -> List[str]:
    kws=[]
    for k in getattr(u,"keywords",[]):
        t=getattr(k,"keyword",None) or getattr(k,"text",None)
        if t:
            t=str(t).strip()
            if t: kws.append(t)
    return kws

def user_active(u: User) -> bool:
    if getattr(u,"is_blocked",False): return False
    lic=getattr(u,"access_until",None) or getattr(u,"license_until",None)
    tri=getattr(u,"trial_until",None) or getattr(u,"trial_ends",None)
    exp=lic or tri
    return bool(exp and exp>=now_utc())

async def fetch_freelancer_for_keyword(client: httpx.AsyncClient, kw: str) -> List[dict]:
    url = (
        "https://www.freelancer.com/api/projects/0.1/projects/active/"
        f"?limit={FREELANCER_LIMIT}&compact=true&user_details=true&job_details=true&full_description=true"
        f"&query={httpx.QueryParams({'q': kw}).get('q') or kw}"
    )
    r = await client.get(url, timeout=SEND_TIMEOUT_SECONDS)
    r.raise_for_status()
    data = r.json()
    projects = (data.get("result") or {}).get("projects") or []
    out=[]
    for p in projects:
        pid=p.get("id")
        if not pid: continue
        title = norm_text(p.get("title") or "")
        if not title: continue
        descr = norm_text((p.get("preview_description") or p.get("description") or "")[:3000])  # full text (safe cap)
        link  = f"https://www.freelancer.com/projects/{pid}"
        b     = p.get("budget") or {}
        curr  = (b.get("currency") or {}).get("code")
        mn, mx = b.get("minimum"), b.get("maximum")
        posted = p.get("publish_time") or p.get("time_submitted")
        posted_dt=None
        try:
            if posted:
                posted_dt=datetime.fromisoformat(str(posted).replace("Z","+00:00")).astimezone(UTC)
        except Exception:
            posted_dt=None
        out.append({
            "source":"Freelancer",
            "source_id":str(pid),
            "title":title,
            "description":descr,
            "url":link,
            "proposal_url":affiliate(link),
            "original_url":affiliate(link),
            "budget_min": float(mn) if mn is not None else None,
            "budget_max": float(mx) if mx is not None else None,
            "budget_currency": curr,
            "job_type": None,
            "bids_count": (p.get("bid_stats") or {}).get("bid_count"),
            "matched_keyword": kw,
            "posted_at": posted_dt,
        })
    return out

async def fetch_skywalker(client: httpx.AsyncClient) -> List[dict]:
    out=[]
    try:
        r=await client.get(SKYWALKER_FEED_URL, timeout=SEND_TIMEOUT_SECONDS)
        r.raise_for_status()
        text=r.text
        items=re.split(r"</item>", text, flags=re.I)
        for raw in items:
            if "<item>" not in raw.lower(): continue
            def gx(tag):
                m=re.search(fr"<{tag}>(.*?)</{tag}>", raw, flags=re.I|re.S)
                return norm_text(html.unescape(m.group(1))) if m else ""
            title=gx("title")
            link=gx("link")
            descr=gx("description")
            if not title: continue
            out.append({
                "source":"Skywalker",
                "source_id": link or title[:100],
                "title": title,
                "description": descr[:3000],
                "url": link,
                "proposal_url": affiliate(link),
                "original_url": affiliate(link),
                "budget_min": None,
                "budget_max": None,
                "budget_currency": None,
                "job_type": None,
                "bids_count": None,
                "matched_keyword": None,
                "posted_at": now_utc(),
            })
    except Exception as e:
        log.warning("Skywalker fetch failed: %s", e)
    return out

def compose_message(job: Job) -> str:
    title = job.title or "Untitled"
    bline=""
    if job.budget_min is not None or job.budget_max is not None or job.budget_currency:
        rng=""
        if job.budget_min is not None and job.budget_max is not None:
            rng=f"{job.budget_min:.1f}–{job.budget_max:.1f} {job.budget_currency or ''}".strip()
        elif job.budget_min is not None:
            rng=f"{job.budget_min:.1f} {job.budget_currency or ''}".strip()
        elif job.budget_max is not None:
            rng=f"{job.budget_max:.1f} {job.budget_currency or ''}".strip()
        usd=usd_range(job.budget_min, job.budget_max, job.budget_currency)
        usd_txt=f" (~{pretty_usd(usd[0], usd[1])})" if usd else ""
        bline=f"🧾 Budget: {rng}{usd_txt}".rstrip()

    src=f"📎 Source: {job.source}"
    mk =f"🔍 Match: {job.matched_keyword}" if getattr(job,"matched_keyword",None) else None
    # 👉 πλήρης περιγραφή (όπως στην ειδοποίηση), με ασφαλές όριο < 4096
    desc=(job.description or "").strip()
    if len(desc) > 3000:
        desc = desc[:3000] + "…"
    when=timeago(getattr(job,"posted_at",None))

    parts=[title]
    if bline: parts.append(bline)
    parts.append(src)
    if mk: parts.append(mk)
    if desc: parts.append(f"📝 {desc}")
    if when: parts.append(f"⏱️ {when}")
    return "\n".join(parts)

def compose_keyboard(job: Job):
    return {
        "inline_keyboard":[
            [
                {"text":"📨 Proposal","url": job.proposal_url or job.original_url or job.url},
                {"text":"🔗 Original","url": job.original_url or job.url or job.proposal_url},
            ],
            [
                {"text":"⭐ Save","callback_data": f"job:save:{job.id}"},
                {"text":"🗑️ Delete","callback_data": f"job:delete:{job.id}"},
            ]
        ]
    }

async def send_to_user(client:httpx.AsyncClient, u:User, job:Job)->bool:
    chat_id=getattr(u,"telegram_id",None) or getattr(u,"tg_id",None) or getattr(u,"chat_id",None)
    if not chat_id: return False
    payload={"chat_id": str(chat_id),
             "text": compose_message(job),
             "reply_markup": compose_keyboard(job),
             "disable_web_page_preview": True}
    try:
        r=await client.post(tg_api("sendMessage"), json=payload, timeout=SEND_TIMEOUT_SECONDS)
        r.raise_for_status()
        return True
    except Exception as e:
        log.warning("send_to_user failed: %s", e)
        return False

async def cycle_once():
    db=SessionLocal()
    sent_count=0
    try:
        users:List[User]=db.query(User).all()
        if not users:
            log.info("No users in DB."); return
        async with httpx.AsyncClient(follow_redirects=True, timeout=SEND_TIMEOUT_SECONDS) as client:
            sky_list=await fetch_skywalker(client)

            def key_of(rec:dict)->str:
                return (rec.get("title") or "").strip().lower()[:60]

            for u in users:
                if not user_active(u): continue
                kws=user_keywords(db,u)
                if not kws: continue

                fl_all=[]
                for kw in kws:
                    try:
                        fl_all += await fetch_freelancer_for_keyword(client, kw)
                    except Exception as e:
                        log.warning("Freelancer fetch failed (%s): %s", kw, e)

                # dedup (Skywalker first, Freelancer last → προτεραιότητα Freelancer)
                pool:Dict[str,dict]={}
                for rec in sky_list + fl_all:
                    pool[key_of(rec)] = rec

                for rec in pool.values():
                    # keyword match guard
                    txt=(rec.get("title","")+" "+rec.get("description","")).lower()
                    matched=False
                    for kw in kws:
                        if kw.lower() in txt:
                            rec["matched_keyword"]=kw
                            matched=True
                            break
                    if not matched: 
                        continue

                    try:
                        j=ensure_job(
                            db,
                            rec["source"], str(rec["source_id"]),
                            title=rec.get("title") or "Untitled",
                            description=rec.get("description") or "",
                            url=rec.get("url"),
                            proposal_url=rec.get("proposal_url"),
                            original_url=rec.get("original_url"),
                            budget_min=rec.get("budget_min"),
                            budget_max=rec.get("budget_max"),
                            budget_currency=rec.get("budget_currency"),
                            job_type=rec.get("job_type"),
                            bids_count=rec.get("bids_count"),
                            matched_keyword=rec.get("matched_keyword"),
                            posted_at=rec.get("posted_at"),
                        )
                    except SQLAlchemyError as e:
                        db.rollback()
                        log.warning("Job upsert failed: %s", e)
                        continue

                    if already_sent(db, u.id, j.id): 
                        continue

                    if await send_to_user(client, u, j):
                        mark_sent(db, u.id, j.id)
                        sent_count += 1

        log.info("Worker cycle complete. Sent %d messages.", sent_count)
    finally:
        try: db.close()
        except Exception: pass

async def run_forever():
    init_db()
    log.info("Worker started. Cycle every %ss", CYCLE_SECONDS)
    while True:
        try:
            await cycle_once()
        except Exception as e:
            log.warning("Cycle error: %s", e)
        await asyncio.sleep(CYCLE_SECONDS)

if __name__ == "__main__":
    asyncio.run(run_forever())
