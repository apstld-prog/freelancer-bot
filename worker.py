# worker.py
# -*- coding: utf-8 -*-
"""
Freelancer Bot - Worker
- Pulls jobs from Skywalker RSS + Freelancer API
- Matches per-user keywords
- Deduplicates (prefer affiliate sources)
- Stores sent items in JobSent for /feedstatus
- Sends Telegram messages with Proposal / Original buttons

Safe: designed to work with the existing db.py models you already use.
"""

import os
import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
import html

import httpx

# --- DB models (defensive import, no schema changes) ---
SessionLocal = None
User = None
Keyword = None
JobSent = None
try:
    from db import SessionLocal as _S, User as _U, Keyword as _K, JobSent as _J, init_db as _init_db
    SessionLocal, User, Keyword, JobSent = _S, _U, _K, _J
except Exception:
    pass

log = logging.getLogger("worker")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

UTC = timezone.utc

# ---- ENV ----
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = (os.getenv("ADMIN_ID") or "").strip()
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "20"))
CYCLE_SECONDS = int(os.getenv("WORKER_INTERVAL", "60"))

# Feeds toggles
FEED_SKY = os.getenv("FEED_SKY", "1") == "1"
FEED_FREELANCER = os.getenv("FEED_FREELANCER", "1") == "1"

# Sources
SKY_FEED_URL = os.getenv("SKY_FEED_URL", "https://www.skywalker.gr/jobs/feed")
FREELANCER_API = "https://www.freelancer.com/api/projects/0.1/projects/active/"

# Affiliate wrapping (keeps wording hidden, used only on link)
AFFILIATE_PREFIX = os.getenv("AFFILIATE_PREFIX", "").strip()  # e.g. "https://yoursub.domain/redirect?u="

# ----------------- helpers -----------------
def now_utc() -> datetime:
    return datetime.now(UTC)

def _get_user_id_field() -> str:
    for cand in ("telegram_id", "tg_id", "chat_id", "user_id", "id"):
        if hasattr(User, cand):
            return cand
    raise RuntimeError("User model must expose a telegram id field.")

def _display_user_id(u) -> str:
    for f in ("telegram_id", "tg_id", "chat_id", "user_id", "id"):
        if hasattr(u, f):
            return str(getattr(u, f))
    return "?"

def _dates_for_user(u) -> Tuple[Optional[datetime], Optional[datetime], Optional[datetime]]:
    trial_start = getattr(u, "started_at", None) or getattr(u, "trial_start", None)
    trial_ends = getattr(u, "trial_until", None) or getattr(u, "trial_ends", None)
    license_until = getattr(u, "access_until", None) or getattr(u, "license_until", None)
    return trial_start, trial_ends, license_until

def _effective_expiry(u) -> Optional[datetime]:
    _, te, lu = _dates_for_user(u)
    return lu or te

def user_is_active(u) -> bool:
    if getattr(u, "is_blocked", False):
        return False
    exp = _effective_expiry(u)
    return bool(exp and exp >= now_utc())

def _list_keywords(db, user) -> List[str]:
    kws: List[str] = []
    if Keyword is None:
        return kws
    try:
        rel = getattr(user, "keywords", None)
        if rel is not None:
            for k in list(rel):
                txt = getattr(k, "keyword", None) or getattr(k, "text", None)
                if txt:
                    kws.append(str(txt))
            return kws
    except Exception:
        pass

    # fallback simple query
    try:
        uid = getattr(user, "id", None)
        if uid is None:
            return kws
        q = db.query(Keyword).filter(Keyword.user_id == uid)
        fld = "keyword" if hasattr(Keyword, "keyword") else "text"
        for k in q.all():
            txt = getattr(k, fld, None)
            if txt:
                kws.append(str(txt))
    except Exception:
        pass
    return kws

def normalize_text(s: str) -> str:
    s = s or ""
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s, flags=re.S).strip()
    return s

def any_keyword_match(text: str, keywords: List[str]) -> bool:
    if not text or not keywords:
        return False
    t = text.lower()
    for w in keywords:
        w = (w or "").strip()
        if not w:
            continue
        if w.lower() in t:
            return True
    return False

def wrap_affiliate(url: str) -> str:
    if not url:
        return url
    if not AFFILIATE_PREFIX:
        return url
    # simple safe wrapper (no visible "affiliate" word)
    import urllib.parse as up
    return f"{AFFILIATE_PREFIX}{up.quote(url, safe='')}"

def build_job_id(prefix: str, raw_id: str) -> str:
    raw = str(raw_id or "").strip()
    return f"{prefix}-{raw}" if raw else f"{prefix}-unknown"

async def send_job(bot_token: str, chat_id: int, text: str, buttons: List[Tuple[str, str]]):
    api = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    kb = {
        "inline_keyboard": [
            [{"text": cap, "url": url}] for cap, url in buttons if url
        ]
    }
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        await client.post(api, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": kb
        })

def _safe_add_jobsent(db, user, job_id: str, source: str, title: str, url: str):
    """Insert a JobSent row if the model supports these fields."""
    if JobSent is None:
        return
    try:
        row = JobSent()
        # Try to set what exists; ignore if field missing
        for f, v in (
            ("user_id", getattr(user, "id", None)),
            ("telegram_id", getattr(user, _get_user_id_field(), None)),
            ("job_id", job_id),
            ("source", source),
            ("title", title),
            ("url", url),
            ("created_at", now_utc()),
        ):
            if hasattr(JobSent, f):
                setattr(row, f, v)
        db.add(row)
        db.commit()
    except Exception as e:
        db.rollback()
        log.warning("JobSent insert failed: %s", e)

def _already_sent(db, user, job_id: str) -> bool:
    if JobSent is None:
        return False
    try:
        q = db.query(JobSent)
        if hasattr(JobSent, "user_id") and hasattr(user, "id"):
            q = q.filter(JobSent.user_id == getattr(user, "id"))
        elif hasattr(JobSent, "telegram_id"):
            q = q.filter(JobSent.telegram_id == getattr(user, _get_user_id_field(), None))
        if hasattr(JobSent, "job_id"):
            q = q.filter(JobSent.job_id == job_id)
        return q.first() is not None
    except Exception:
        return False

# ----------------- Feeds -----------------
async def fetch_skywalker() -> List[Dict]:
    """Return list of dicts: {id,title,desc,url,source}"""
    if not FEED_SKY:
        return []
    out: List[Dict] = []
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.get(SKY_FEED_URL)
            r.raise_for_status()
            xml = r.text
    except Exception as e:
        log.warning("Skywalker fetch failed: %s", e)
        return out

    # lightweight RSS parse (no extra deps)
    # <item><title>..</title><link>..</link><guid>..</guid><description>..</description></item>
    items = re.findall(r"<item>(.*?)</item>", xml, flags=re.S)
    for it in items:
        title = normalize_text("".join(re.findall(r"<title>(.*?)</title>", it, flags=re.S)))
        link = normalize_text("".join(re.findall(r"<link>(.*?)</link>", it, flags=re.S)))
        guid = normalize_text("".join(re.findall(r"<guid.*?>(.*?)</guid>", it, flags=re.S))) or link
        desc = normalize_text("".join(re.findall(r"<description>(.*?)</description>", it, flags=re.S)))
        if not title and not link:
            continue
        out.append({
            "id": build_job_id("sky", guid or link or title),
            "title": title,
            "desc": desc,
            "url": link,
            "source": "Skywalker",
            "affiliate": False,
        })
    log.info("Skywalker fetched %d items", len(out))
    return out

async def fetch_freelancer_for_queries(queries: List[str]) -> List[Dict]:
    if not FEED_FREELANCER or not queries:
        return []
    out: List[Dict] = []
    params_base = {
        "limit": 30,
        "compact": "true",
        "user_details": "true",
        "job_details": "true",
        "full_description": "true",
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
                pid = p.get("id")
                title = p.get("title") or ""
                desc = p.get("description") or ""
                currency = (p.get("currency") or {}).get("code") or ""
                budget_min = (p.get("budget") or {}).get("minimum") or ""
                budget_max = (p.get("budget") or {}).get("maximum") or ""
                url = f"https://www.freelancer.com/projects/{pid}"
                out.append({
                    "id": build_job_id("freelancer", str(pid)),
                    "title": normalize_text(title),
                    "desc": normalize_text(desc),
                    "url": url,
                    "source": "Freelancer",
                    "affiliate": True,  # prefer in dedup
                    "budget": f"{budget_min}-{budget_max} {currency}".strip("- "),
                })
    log.info("Freelancer fetched ~%d items (merged)", len(out))
    return out

# --------------- Matching & delivery ----------------
def dedup_prefer_affiliate(items: List[Dict]) -> List[Dict]:
    """Dedup by normalized title/url. Prefer affiliate=True version."""
    seen: Dict[str, Dict] = {}
    for it in items:
        key = (it.get("title") or "").lower().strip()
        if not key:
            key = (it.get("url") or "").lower().strip()
        prev = seen.get(key)
        if not prev:
            seen[key] = it
        else:
            if it.get("affiliate") and not prev.get("affiliate"):
                seen[key] = it
    return list(seen.values())

async def process_for_user(db, user, all_items: List[Dict]):
    # gather user keywords
    kws_raw = _list_keywords(db, user)
    keywords = sorted({k.strip() for k in kws_raw if k and str(k).strip()})
    if not keywords:
        return 0

    # filter by keywords on title/desc
    matches: List[Dict] = []
    for it in all_items:
        text_blob = f"{it.get('title','')} {it.get('desc','')}"
        if any_keyword_match(text_blob, keywords):
            matches.append(it)

    # prefer affiliate among duplicates (per-user)
    matches = dedup_prefer_affiliate(matches)

    # send
    sent = 0
    chat_id = getattr(user, _get_user_id_field(), None)
    if not chat_id:
        return 0

    for it in matches:
        job_id = it.get("id") or ""
        if _already_sent(db, user, job_id):
            continue

        title = it.get("title") or "(no title)"
        url_original = it.get("url") or ""
        url_wrapped = wrap_affiliate(url_original)

        # Compose message
        parts = [f"<b>{html.escape(title)}</b>"]
        if it.get("budget"):
            parts.append(f"💵 Budget: {html.escape(it['budget'])}")
        parts.append(f"📎 Source: {it.get('source')}")
        text = "\n".join(parts)

        # Buttons (no 'affiliate' wording)
        buttons = [
            ("📨 Proposal", url_wrapped or url_original),
            ("🔗 Original", url_wrapped or url_original),
        ]

        try:
            await send_job(BOT_TOKEN, int(chat_id), text, buttons)
            _safe_add_jobsent(db, user, job_id, it.get("source") or "", title, url_wrapped or url_original)
            sent += 1
        except Exception as e:
            log.warning("Send failed to %s: %s", _display_user_id(user), e)

    return sent

async def worker_cycle():
    if SessionLocal is None or User is None:
        log.warning("DB not available; skipping cycle")
        return

    # Ensure DB schema once
    try:
        if '_init_db' in globals() and callable(_init_db):
            _init_db()
    except Exception:
        pass

    db = SessionLocal()
    try:
        users: List[User] = list(db.query(User).all())
    except Exception as e:
        log.warning("DB read users failed: %s", e)
        try:
            db.close()
        except Exception:
            pass
        return

    # fetch once per cycle (global)
    items: List[Dict] = []
    sky, fr = [], []
    try:
        if FEED_SKY:
            sky = await fetch_skywalker()
        if FEED_FREELANCER:
            # union of all keywords across active users for API efficiency
            all_kws = set()
            for u in users:
                if user_is_active(u):
                    for k in _list_keywords(db, u):
                        k = (k or "").strip()
                        if k:
                            all_kws.add(k)
            fr = await fetch_freelancer_for_queries(sorted(all_kws)[:20])  # cap to 20 queries per cycle
    except Exception as e:
        log.warning("Fetch error: %s", e)

    items.extend(sky)
    items.extend(fr)

    # deliver per-user
    total = 0
    for u in users:
        if not user_is_active(u):
            continue
        try:
            total += await process_for_user(db, u, items)
        except Exception as e:
            log.warning("Process user %s failed: %s", _display_user_id(u), e)

    try:
        db.close()
    except Exception:
        pass

    log.info("Worker cycle complete. Sent %d messages.", total)

# --------------- entrypoint ---------------
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
