# worker.py
# -*- coding: utf-8 -*-
"""
Freelancer Bot - Worker
- Pulls jobs from Skywalker RSS + Freelancer API
- Matches per-user keywords
- Deduplicates (prefer affiliate sources)
- Upserts into job, logs in job_sent (per user)
- Sends Telegram messages with Proposal/Original + Save/Delete (2 ανά σειρά)
"""

import os
import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import html
import json

import httpx

# ---- DB wiring (no schema changes) ----
SessionLocal = None
User = None
Keyword = None
Job = None
JobSent = None
try:
    from db import (
        SessionLocal as _S,
        User as _U,
        Keyword as _K,
        Job as _J,
        JobSent as _JS,
        init_db as _init_db,
    )
    SessionLocal, User, Keyword, Job, JobSent = _S, _U, _K, _J, _JS
except Exception:
    pass

log = logging.getLogger("worker")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

UTC = timezone.utc

# ---- ENV ----
BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "20"))
CYCLE_SECONDS = int(os.getenv("WORKER_INTERVAL", "60"))

FEED_SKY = os.getenv("FEED_SKY", "1") == "1"
FEED_FREELANCER = os.getenv("FEED_FREELANCER", "1") == "1"

SKY_FEED_URL = os.getenv("SKY_FEED_URL", "https://www.skywalker.gr/jobs/feed")
FREELANCER_API = "https://www.freelancer.com/api/projects/0.1/projects/active/"

# Δεν εμφανίζουμε “affiliate” στη λέξη, απλώς τυλίγουμε το URL.
AFFILIATE_PREFIX = (os.getenv("AFFILIATE_PREFIX") or "").strip()  # e.g. https://x/redirect?u=

_DEFAULT_FX = {
    "USD": 1.0, "EUR": 1.08, "GBP": 1.27, "CAD": 0.73, "AUD": 0.65,
    "CHF": 1.10, "JPY": 0.0066, "NOK": 0.091, "SEK": 0.091, "DKK": 0.145,
}
try:
    FX_RATES = json.loads(os.getenv("FX_RATES", "")) if os.getenv("FX_RATES") else _DEFAULT_FX
except Exception:
    FX_RATES = _DEFAULT_FX


# ----------------- helpers -----------------
def now_utc() -> datetime:
    return datetime.now(UTC)

def _uid_field() -> str:
    for c in ("telegram_id", "tg_id", "chat_id", "user_id", "id"):
        if hasattr(User, c):
            return c
    raise RuntimeError("User model must expose a telegram id field")

def user_active(u) -> bool:
    if getattr(u, "is_blocked", False):
        return False
    exp = getattr(u, "access_until", None) or getattr(u, "license_until", None) or getattr(u, "trial_until", None)
    return bool(exp and exp >= now_utc())

def _kws(db, u) -> List[str]:
    out: List[str] = []
    if Keyword is None:
        return out
    try:
        rel = getattr(u, "keywords", None)
        if rel is not None:
            for k in list(rel):
                t = getattr(k, "keyword", None) or getattr(k, "text", None)
                if t:
                    out.append(str(t))
            return out
    except Exception:
        pass
    try:
        uid = getattr(u, "id", None)
        fld = "keyword" if hasattr(Keyword, "keyword") else "text"
        for k in db.query(Keyword).filter(Keyword.user_id == uid).all():
            t = getattr(k, fld, None)
            if t:
                out.append(str(t))
    except Exception:
        pass
    return out

def norm(s: str) -> str:
    s = s or ""
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s, flags=re.S).strip()

def match_kw(blob: str, kws: List[str]) -> Optional[str]:
    t = (blob or "").lower()
    for w in kws:
        w2 = (w or "").strip()
        if w2 and w2.lower() in t:
            return w2
    return None

def wrap(url: str) -> str:
    if not url or not AFFILIATE_PREFIX:
        return url
    import urllib.parse as up
    return f"{AFFILIATE_PREFIX}{up.quote(url, safe='')}"

def usd_range(mn, mx, cur):
    code = (cur or "USD").upper()
    rate = float(FX_RATES.get(code, 1.0))
    try:
        vmin = float(mn) if mn is not None else None
        vmax = float(mx) if mx is not None else None
    except Exception:
        return None
    conv = lambda v: round(float(v) * rate, 2) if v is not None else None
    umin, umax = conv(vmin), conv(vmax)
    if umin is None and umax is None: return None
    if umin is None: return f"~${umax}"
    if umax is None: return f"~${umin}"
    return f"~${umin}–{umax}"

def age(ts: Optional[datetime]) -> str:
    if not ts: return "unknown"
    s = max(0, int((now_utc() - ts).total_seconds()))
    if s < 60: return f"{s}s ago"
    m = s // 60
    if m < 60: return f"{m}m ago"
    h = m // 60
    if h < 24: return f"{h}h ago"
    d = h // 24
    return f"{d}d ago"

def _snippet(s: str, n=220) -> str:
    s = (s or "").strip()
    return (s[:n] + "…") if len(s) > n else s

# ---------- BUTTON LAYOUT (2 per row) ----------
async def _send(bot_token, chat_id, text, url_btns, cb_btns):
    api = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    kb = {"inline_keyboard": []}
    if url_btns:
        kb["inline_keyboard"].append([{"text": t, "url": u} for t, u in url_btns if u])
    if cb_btns:
        kb["inline_keyboard"].append([{"text": t, "callback_data": d} for t, d in cb_btns if d])
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        await client.post(api, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": kb
        })

# ----------------- DB helpers -----------------
def get_or_create_job(
    db,
    *,
    source: str,
    source_id: str,
    title: str,
    desc: str,
    url: str,
    proposal_url: str,
    original_url: str,
    bmin: Optional[float],
    bmax: Optional[float],
    currency: Optional[str],
    matched: Optional[str],
    posted_at: Optional[datetime],
) -> int:
    """Upsert στον πίνακα job βάσει (source, source_id). Επιστρέφει job.id (int)."""
    # SAFE defaults για NOT NULL πεδία
    title = (title or "Untitled Job").strip()[:512]
    url = (url or "").strip()
    if not url:
        raise ValueError("Job url is empty")
    desc = (desc or "").strip()
    proposal_url = (proposal_url or url).strip()
    original_url = (original_url or url).strip()
    currency = (currency or "USD")[:16]
    when = posted_at or now_utc()

    try:
        db.rollback()
    except Exception:
        pass

    row = db.query(Job).filter(Job.source == source, Job.source_id == str(source_id)).one_or_none()
    if not row:
        row = Job(source=source, source_id=str(source_id))
        db.add(row)
        db.flush()

    row.title = title
    row.description = desc
    row.url = url
    row.proposal_url = proposal_url
    row.original_url = original_url
    row.budget_min = bmin
    row.budget_max = bmax
    row.budget_currency = currency
    row.matched_keyword = matched
    row.posted_at = when

    try:
        db.commit()
    except Exception:
        try: db.rollback()
        except Exception: pass
        raise
    return int(row.id)

def add_jobsent(db, user_id: int, job_id: int):
    try: db.rollback()
    except Exception: pass
    try:
        js = JobSent(user_id=int(user_id), job_id=int(job_id))
        db.add(js)
        db.commit()
    except Exception as e:
        try: db.rollback()
        except Exception: pass
        log.warning("JobSent insert failed: %s", e)

# ----------------- Feeds -----------------
async def fetch_skywalker() -> List[Dict]:
    if not FEED_SKY:
        return []
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.get(SKY_FEED_URL)
            r.raise_for_status()
            xml = r.text
    except Exception as e:
        log.warning("Skywalker fetch failed: %s", e)
        return []

    items = re.findall(r"<item>(.*?)</item>", xml, flags=re.S)
    out: List[Dict] = []
    for it in items:
        title = norm("".join(re.findall(r"<title>(.*?)</title>", it, flags=re.S))) or "Untitled Job"
        link = norm("".join(re.findall(r"<link>(.*?)</link>", it, flags=re.S)))
        if not link:
            continue  # δεν γράφουμε χωρίς URL
        guid = norm("".join(re.findall(r"<guid.*?>(.*?)</guid>", it, flags=re.S))) or link
        desc = norm("".join(re.findall(r"<description>(.*?)</description>", it, flags=re.S)))
        pub = norm("".join(re.findall(r"<pubDate>(.*?)</pubDate>", it, flags=re.S)))
        when = None
        if pub:
            try:
                from email.utils import parsedate_to_datetime
                when = parsedate_to_datetime(pub)
                if when.tzinfo is None:
                    when = when.replace(tzinfo=UTC)
            except Exception:
                when = now_utc()
        out.append({
            "source": "Skywalker", "source_id": guid or link or title,
            "title": title, "desc": desc, "url": link,
            "proposal": link, "original": link,
            "budget_min": None, "budget_max": None, "currency": None,
            "posted_at": when or now_utc(),
        })
    return out

async def fetch_freelancer_for_queries(queries: List[str]) -> List[Dict]:
    if not FEED_FREELANCER or not queries:
        return []
    out: List[Dict] = []
    params_base = {
        "limit": 30, "compact": "true",
        "user_details": "true", "job_details": "true", "full_description": "true",
    }
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        for q in queries:
            try:
                resp = await client.get(FREELANCER_API, params={**params_base, "query": q})
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                log.warning("Freelancer fetch failed (%s): %s", q, e)
                continue

            projects = (data.get("result") or {}).get("projects") or []
            for p in projects:
                pid = str(p.get("id") or "").strip()
                raw_title = (p.get("title") or "").strip()
                title = raw_title if raw_title else (f"Untitled Job #{pid}" if pid else "Untitled Job")
                desc = (p.get("description") or "").strip()
                url = f"https://www.freelancer.com/projects/{pid}" if pid else ""
                if not url:
                    continue

                currency = ((p.get("currency") or {}).get("code") or "USD").upper()
                bmin = (p.get("budget") or {}).get("minimum")
                bmax = (p.get("budget") or {}).get("maximum")
                ts = p.get("time_submitted") or p.get("submitdate")
                posted_at = None
                if ts:
                    try:
                        posted_at = datetime.fromtimestamp(int(ts), tz=UTC)
                    except Exception:
                        posted_at = now_utc()

                out.append({
                    "source": "Freelancer", "source_id": pid or "unknown",
                    "title": norm(title), "desc": norm(desc),
                    "url": url,
                    "proposal": wrap(url), "original": url,
                    "budget_min": bmin, "budget_max": bmax, "currency": currency,
                    "posted_at": posted_at or now_utc(),
                })
    log.info("Freelancer fetched ~%d items (merged)", len(out))
    return out

# --------------- Matching & delivery ----------------
def dedup_prefer_affiliate(items: List[Dict]) -> List[Dict]:
    seen: Dict[str, Dict] = {}
    for it in items:
        key = (it.get("title") or "").lower().strip() or (it.get("url") or "").lower().strip()
        prev = seen.get(key)
        if not prev:
            seen[key] = it
        else:
            a = bool(it.get("proposal")) and it["proposal"] != it["url"]
            a0 = bool(prev.get("proposal")) and prev["proposal"] != prev["url"]
            if a and not a0:
                seen[key] = it
    return list(seen.values())

async def process_user(db, user, items) -> int:
    kws = [k for k in _kws(db, user) if k]
    if not kws:
        return 0

    matches: List[Dict] = []
    for it in items:
        mk = match_kw(f"{it['title']} {it['desc']}", kws)
        if mk:
            x = dict(it)
            x["_matched"] = mk
            matches.append(x)
    matches = dedup_prefer_affiliate(matches)

    chat_id = getattr(user, _uid_field(), None)
    if not chat_id:
        return 0

    sent = 0
    for it in matches:
        # Upsert job -> id
        try:
            jid = get_or_create_job(
                db,
                source=it["source"], source_id=str(it["source_id"]),
                title=it["title"], desc=it["desc"],
                url=it["url"], proposal_url=it.get("proposal"), original_url=it.get("original"),
                bmin=it.get("budget_min"), bmax=it.get("budget_max"), currency=it.get("currency"),
                matched=it.get("_matched"), posted_at=it.get("posted_at"),
            )
        except Exception as e:
            log.warning("Job upsert failed: %s", e)
            try: db.rollback()
            except Exception: pass
            continue

        # Skip if already sent to this user
        try: db.rollback()
        except Exception: pass
        already = db.query(JobSent).filter(
            JobSent.user_id == getattr(user, "id"), JobSent.job_id == jid
        ).first()
        if already:
            continue

        # Build message
        raw = None; usd = None
        if it.get("budget_min") is not None or it.get("budget_max") is not None:
            bmin = "" if it.get("budget_min") is None else str(it.get("budget_min"))
            bmax = "" if it.get("budget_max") is None else str(it.get("budget_max"))
            raw = f"{bmin}-{bmax} {it.get('currency')}".strip("- ")
            usd = usd_range(it.get("budget_min"), it.get("budget_max"), it.get("currency"))

        match_disp = f"<b><u>{html.escape(it.get('_matched') or '')}</u></b>" if it.get("_matched") else None
        lines = [f"<b>{html.escape(it['title'])}</b>"]
        if raw:
            lines.append(f"🧾 Budget: {html.escape(raw)}" + (f" ({usd})" if usd else ""))
        lines.append(f"📎 Source: {it['source']}")
        if match_disp:
            lines.append(f"🔍 Match: {match_disp}")
        sn = _snippet(it.get("desc") or "")
        if sn:
            lines.append(f"📝 {html.escape(sn)}")
        lines.append(f"⏱️ {age(it.get('posted_at'))}")
        text = "\n".join(lines)

        url_buttons = [
            ("📨 Proposal", it.get("proposal") or it["url"]),
            ("🔗 Original",  it.get("proposal") or it["url"]),
        ]
        cb_buttons = [
            ("⭐ Save",   f"job:save:{jid}"),
            ("🗑️ Delete", f"job:delete:{jid}"),
        ]

        try:
            await _send(BOT_TOKEN, int(chat_id), text, url_buttons, cb_buttons)
            add_jobsent(db, getattr(user, "id"), jid)
            sent += 1
        except Exception as e:
            log.warning("Send failed to %s: %s", getattr(user, _uid_field(), None), e)
            try: db.rollback()
            except Exception: pass

    return sent

async def worker_cycle():
    if None in (SessionLocal, User, Job, JobSent):
        log.warning("DB not available; skipping")
        return
    try:
        if '_init_db' in globals() and callable(_init_db):
            _init_db()
    except Exception:
        pass

    db = SessionLocal()
    try:
        users = list(db.query(User).all())
    except Exception as e:
        log.warning("DB users read failed: %s", e)
        try: db.close()
        except Exception: pass
        return

    # fetch feeds
    items: List[Dict] = []
    try:
        sky = await fetch_skywalker() if FEED_SKY else []
        fr: List[Dict] = []
        if FEED_FREELANCER:
            all_k = set()
            for u in users:
                if user_active(u):
                    for k in _kws(db, u):
                        k = (k or "").strip()
                        if k:
                            all_k.add(k)
            fr = await fetch_freelancer_for_queries(sorted(all_k)[:20])
        items = sky + fr
    except Exception as e:
        log.warning("Fetch error: %s", e)

    total = 0
    for u in users:
        if not user_active(u):
            continue
        try:
            total += await process_user(db, u, items)
        except Exception as e:
            log.warning("Process user failed: %s", e)
            try: db.rollback()
            except Exception: pass

    try: db.close()
    except Exception: pass
    log.info("Worker cycle complete. Sent %d messages.", total)

async def main():
    log.info("Worker started. Cycle every %ss", CYCLE_SECONDS)
    while True:
        try:
            await worker_cycle()
        except Exception as e:
            log.warning("Cycle error: %s", e)
        await asyncio.sleep(CYCLE_SECONDS)

if __name__ == "__main__":
    asyncio.run(main())
