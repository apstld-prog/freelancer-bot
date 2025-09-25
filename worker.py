import os
import time
import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import List, Dict, Optional, Set
from urllib.parse import quote_plus

import requests
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton

from db import SessionLocal, User, Keyword, JobSent

# ==============================================================================
# ENV / CORE
# ==============================================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "90"))
DEBUG = os.getenv("DEBUG", "0") == "1"
MOCK_JOBS = os.getenv("MOCK_JOBS", "0") == "1"

# Sources toggles
FREELANCER_ENABLED = os.getenv("FREELANCER_ENABLED", "1") == "1"
REMOTEOK_ENABLED   = os.getenv("REMOTEOK_ENABLED", "1") == "1"
WWR_ENABLED        = os.getenv("WWR_ENABLED", "1") == "1"
REMOTIVE_ENABLED   = os.getenv("REMOTIVE_ENABLED", "1") == "1"

# HTTP/retry
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "15"))
HTTP_RETRIES = int(os.getenv("HTTP_RETRIES", "3"))
HTTP_BACKOFF = float(os.getenv("HTTP_BACKOFF", "1.6"))

# Affiliate
FREELANCER_AFFILIATE_ID = os.getenv("FREELANCER_AFFILIATE_ID", "")
FIVERR_AFFILIATE_ID     = os.getenv("FIVERR_AFFILIATE_ID", "")

# Global filters (source-agnostic, applied where data available)
MAX_AGE_MIN       = int(os.getenv("MAX_AGE_MIN", "180"))
MIN_BUDGET        = int(os.getenv("MIN_BUDGET", "0"))
MIN_HOURLY        = float(os.getenv("MIN_HOURLY", "0"))      # hourly lower bound
MAX_HOURLY        = float(os.getenv("MAX_HOURLY", "0"))      # 0 means "no max"
INCLUDE_TYPES     = {t.strip().upper() for t in os.getenv("INCLUDE_TYPES", "").split(",") if t.strip()}  # FIXED,HOURLY
REQUIRED_SKILLS   = {s.strip().lower() for s in os.getenv("REQUIRED_SKILLS", "").split(",") if s.strip()}
EXCLUDED_SKILLS   = {s.strip().lower() for s in os.getenv("EXCLUDED_SKILLS", "").split(",") if s.strip()}
REQUIRED_KEYWORDS = [s.strip().lower() for s in os.getenv("REQUIRED_KEYWORDS", "").split(",") if s.strip()]
EXCLUDED_KEYWORDS = [s.strip().lower() for s in os.getenv("EXCLUDED_KEYWORDS", "").split(",") if s.strip()]
MAX_SEND_PER_LOOP = int(os.getenv("MAX_SEND_PER_LOOP", "8"))

# Per-source pagination/limits
FREELANCER_LIMIT = int(os.getenv("FREELANCER_LIMIT", "20"))
FREELANCER_PAGES = int(os.getenv("FREELANCER_PAGES", "2"))
REMOTEOK_LIMIT   = int(os.getenv("REMOTEOK_LIMIT", "30"))
WWR_LIMIT        = int(os.getenv("WWR_LIMIT", "30"))
REMOTIVE_LIMIT   = int(os.getenv("REMOTIVE_LIMIT", "30"))

# ------------------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------------------
log_level = logging.DEBUG if DEBUG else logging.INFO
logging.basicConfig(level=log_level, format="%(asctime)s [worker] %(levelname)s: %(message)s")
logger = logging.getLogger("jobs-worker")

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
if not BOT_TOKEN:
    logger.warning("BOT_TOKEN is empty! Worker cannot send Telegram messages.")

# ==============================================================================
# Helpers
# ==============================================================================
def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)

def ts_now() -> int:
    return int(utc_now().timestamp())

def backoff_sleep(attempt: int):
    time.sleep(HTTP_BACKOFF ** (attempt - 1))

def norm_text(*parts: str) -> str:
    return " ".join((p or "").lower() for p in parts)

def countries_list(csv_value: Optional[str]) -> List[str]:
    return [c.strip().upper() for c in (csv_value or "").split(",") if c.strip()]

def keyword_hit(text: str, required: List[str], excluded: List[str]) -> bool:
    if required and not all(k in text for k in required):
        return False
    if excluded and any(k in text for k in excluded):
        return False
    return True

def within_age(ts: Optional[int], max_age_min: int) -> bool:
    if not ts:
        return True
    age_min = (ts_now() - ts) / 60.0
    return age_min <= max_age_min

def build_affiliate_link(platform: str, job_url: str) -> str:
    p = (platform or "").lower()
    if p == "freelancer" and FREELANCER_AFFILIATE_ID:
        return f"https://www.freelancer.com/get/{FREELANCER_AFFILIATE_ID}"
    if p == "fiverr" and FIVERR_AFFILIATE_ID:
        return f"https://track.fiverr.com/visit/?bta={FIVERR_AFFILIATE_ID}&brand=fiverrcpa&url={quote_plus(job_url)}"
    return job_url

# Hourly filter helper
def hourly_ok(rate: Optional[float]) -> bool:
    if rate is None:
        return True  # if we don't know, don't drop
    if rate < MIN_HOURLY:
        return False
    if MAX_HOURLY > 0 and rate > MAX_HOURLY:
        return False
    return True

# ==============================================================================
# HTTP helpers
# ==============================================================================
def http_json(url: str, params: Optional[dict] = None, headers: Optional[dict] = None) -> Optional[dict]:
    h = {"Accept": "application/json", "User-Agent": "FreelancerAlertsBot/1.3"}; h.update(headers or {})
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            r = requests.get(url, params=params, headers=h, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.warning(f"[http_json] GET failed ({attempt}/{HTTP_RETRIES}): {e}")
            backoff_sleep(attempt)
    return None

def http_text(url: str, params: Optional[dict] = None, headers: Optional[dict] = None) -> Optional[str]:
    h = {"User-Agent": "FreelancerAlertsBot/1.3"}; h.update(headers or {})
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            r = requests.get(url, params=params, headers=h, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            return r.text
        except Exception as e:
            logger.warning(f"[http_text] GET failed ({attempt}/{HTTP_RETRIES}): {e}")
            backoff_sleep(attempt)
    return None

# ==============================================================================
# FREELANCER.COM
# ==============================================================================
FREELANCER_API = "https://www.freelancer.com/api/projects/0.1/projects/active/"

def fl_project_country(p: dict) -> Optional[str]:
    owner = p.get("owner") or p.get("employer")
    if not isinstance(owner, dict):
        return None
    loc = owner.get("location") or {}
    country = loc.get("country") or {}
    code = country.get("code")
    name = country.get("name")
    return (code or name or None) and str((code or name)).upper()

def fl_project_url(p: dict) -> str:
    seo_url = p.get("seo_url")
    if isinstance(seo_url, str) and seo_url.startswith("http"):
        return seo_url
    pid = p.get("id")
    return f"https://www.freelancer.com/projects/{pid}"

def fl_project_type(p: dict) -> Optional[str]:
    t = (p.get("type") or "").upper()
    if t in {"FIXED", "HOURLY"}:
        return t
    b = p.get("budget") or {}
    t2 = (b.get("type") or "").upper()
    if t2 in {"FIXED", "HOURLY"}:
        return t2
    return None

def fl_project_skills(p: dict) -> Set[str]:
    jobs = p.get("jobs") or []
    return {str(j.get("name")).lower() for j in jobs if j.get("name")}

def fetch_freelancer(keyword: str, limit: int, pages: int) -> List[Dict]:
    if not FREELANCER_ENABLED:
        return []
    items: List[Dict] = []
    seen: Set[str] = set()
    for page in range(pages):
        params = {
            "query": keyword,
            "limit": str(limit),
            "offset": str(page * limit),
            "full_description": "true",
            "job_details": "true",
            "compact": "true",
        }
        data = http_json(FREELANCER_API, params=params)
        if not data:
            break
        projects = data.get("result", {}).get("projects", []) or []
        logger.debug(f"[freelancer] keyword='{keyword}' page={page} -> {len(projects)}")
        if not projects: break

        for p in projects:
            pid = str(p.get("id") or "")
            if not pid or pid in seen:
                continue
            seen.add(pid)

            # timestamps
            ts = int(p.get("time_updated") or p.get("time_submitted") or 0)
            if not within_age(ts if ts else None, MAX_AGE_MIN):
                continue

            # budget / hourly
            budget = p.get("budget") or {}
            bmin = budget.get("minimum")
            btype = (budget.get("type") or "").upper()

            if bmin is not None and isinstance(bmin, (int, float)) and bmin < MIN_BUDGET:
                continue

            ptype = fl_project_type(p) or "UNKNOWN"
            if INCLUDE_TYPES and ptype not in INCLUDE_TYPES:
                continue

            # Rough hourly threshold: if explicitly hourly, treat minimum as hourly min (API has limited structure)
            if ptype == "HOURLY":
                hr_min = None
                try:
                    # Some payloads expose hourly minimum in "budget" minimum (no fx conversion)
                    hr_min = float(bmin) if bmin is not None else None
                except Exception:
                    hr_min = None
                if not hourly_ok(hr_min):
                    continue

            # skills filter
            skills = fl_project_skills(p)
            if REQUIRED_SKILLS and not REQUIRED_SKILLS.issubset(skills):
                continue
            if EXCLUDED_SKILLS and (EXCLUDED_SKILLS & skills):
                continue

            # text keywords
            txt = norm_text(p.get("title"), p.get("preview_description"))
            if not keyword_hit(txt, REQUIRED_KEYWORDS, EXCLUDED_KEYWORDS):
                continue

            items.append({
                "id": f"fre-{pid}",
                "title": p.get("title") or "Untitled project",
                "url": fl_project_url(p),
                "country": fl_project_country(p) or "ANY",
                "platform": "freelancer",
            })
        time.sleep(0.3)
    return items

# ==============================================================================
# REMOTEOK
# ==============================================================================
REMOTEOK_API = "https://remoteok.com/api"

def fetch_remoteok(keyword: str, cap: int) -> List[Dict]:
    if not REMOTEOK_ENABLED:
        return []
    txt = http_text(REMOTEOK_API)
    if not txt:
        return []
    try:
        arr = json.loads(txt)
    except Exception:
        return []
    out: List[Dict] = []
    for obj in arr:
        if not isinstance(obj, dict) or "id" not in obj:
            continue
        title = obj.get("position") or obj.get("title") or ""
        company = obj.get("company") or ""
        desc = obj.get("description") or ""
        url = obj.get("url") or obj.get("apply_url") or obj.get("canonical_url") or ""
        ts = None
        if obj.get("epoch"):
            try: ts = int(obj["epoch"])
            except Exception: ts = None

        text_all = norm_text(title, company, desc, keyword)
        if keyword and keyword.lower() not in text_all:
            continue
        if not keyword_hit(text_all, REQUIRED_KEYWORDS, EXCLUDED_KEYWORDS):
            continue
        if not within_age(ts, MAX_AGE_MIN):
            continue

        out.append({
            "id": f"rok-{obj['id']}",
            "title": f"{title} @ {company}".strip() or "RemoteOK job",
            "url": url or "https://remoteok.com",
            "country": "ANY",
            "platform": "remoteok",
        })
        if len(out) >= cap:
            break
    return out

# ==============================================================================
# WE WORK REMOTELY (RSS)
# ==============================================================================
WWR_RSS = "https://weworkremotely.com/remote-jobs.rss"

def fetch_wwr(keyword: str, cap: int) -> List[Dict]:
    if not WWR_ENABLED:
        return []
    xml = http_text(WWR_RSS)
    if not xml:
        return []
    try:
        root = ET.fromstring(xml)
    except Exception:
        return []
    items = root.findall("./channel/item")
    out: List[Dict] = []
    for it in items:
        title = (it.findtext("title") or "").strip()
        link  = (it.findtext("link") or "").strip()
        desc  = (it.findtext("description") or "").strip()
        text_all = norm_text(title, desc, keyword)
        if keyword and keyword.lower() not in text_all:
            continue
        if not keyword_hit(text_all, REQUIRED_KEYWORDS, EXCLUDED_KEYWORDS):
            continue
        out.append({
            "id": f"wwr-{hash(link)}",
            "title": title or "WWR job",
            "url": link or "https://weworkremotely.com",
            "country": "ANY",
            "platform": "weworkremotely",
        })
        if len(out) >= cap:
            break
    return out

# ==============================================================================
# REMOTIVE (real API)
# ==============================================================================
REMOTIVE_API = "https://remotive.com/api/remote-jobs"

def fetch_remotive(keyword: str, cap: int) -> List[Dict]:
    if not REMOTIVE_ENABLED:
        return []
    params = {"search": keyword} if keyword else {}
    data = http_json(REMOTIVE_API, params=params)
    if not data:
        return []
    jobs = data.get("jobs") or []
    out: List[Dict] = []
    for j in jobs:
        title = j.get("title") or ""
        company = j.get("company_name") or ""
        desc = j.get("description") or ""
        url = j.get("url") or j.get("job_url") or ""
        pub = j.get("publication_date")
        ts = None
        # publication_date is ISO8601, try to parse quickly
        try:
            if pub:
                # '2025-09-25T10:12:34+00:00'
                ts = int(datetime.fromisoformat(pub.replace("Z", "+00:00")).timestamp())
        except Exception:
            ts = None

        text_all = norm_text(title, company, desc, keyword)
        if keyword and keyword.lower() not in text_all:
            continue
        if not keyword_hit(text_all, REQUIRED_KEYWORDS, EXCLUDED_KEYWORDS):
            continue
        if not within_age(ts, MAX_AGE_MIN):
            continue

        # Remotive sometimes lists salary in 'salary' field like '$40k – $60k' (not parsed here).
        out.append({
            "id": f"rmt-{j.get('id')}",
            "title": f"{title} @ {company}".strip() or "Remotive job",
            "url": url or "https://remotive.com/remote-jobs",
            "country": "ANY",
            "platform": "remotive",
        })
        if len(out) >= cap:
            break
    return out

# ==============================================================================
# MOCK (for tests)
# ==============================================================================
def mock_jobs(keyword: str, n: int = 3) -> List[Dict]:
    now = ts_now()
    return [{
        "id": f"mock-{keyword}-{now}-{i}",
        "title": f"[Mock] {keyword} project #{i+1}",
        "url": "https://www.freelancer.com",
        "country": "ANY",
        "platform": "mock",
    } for i in range(n)]

# ==============================================================================
# AGGREGATOR
# ==============================================================================
def fetch_jobs(keyword: str, user_countries_csv: Optional[str]) -> List[Dict]:
    jobs: List[Dict] = []

    if MOCK_JOBS:
        jobs.extend(mock_jobs(keyword, 3))
    else:
        if FREELANCER_ENABLED:
            jobs.extend(fetch_freelancer(keyword, FREELANCER_LIMIT, FREELANCER_PAGES))
        if REMOTEOK_ENABLED:
            jobs.extend(fetch_remoteok(keyword, REMOTEOK_LIMIT))
        if WWR_ENABLED:
            jobs.extend(fetch_wwr(keyword, WWR_LIMIT))
        if REMOTIVE_ENABLED:
            jobs.extend(fetch_remotive(keyword, REMOTIVE_LIMIT))

    # User-specific country filter (ANY always allowed)
    user_countries = countries_list(user_countries_csv)
    if user_countries:
        before = len(jobs)
        allow = set(user_countries + ["ANY"])
        jobs = [j for j in jobs if (j.get("country") or "ANY").upper() in allow]
        logger.debug(f"[filter] countries={user_countries} kept {len(jobs)}/{before} jobs")

    return jobs

# ==============================================================================
# SEND
# ==============================================================================
def send_job(uid: int, job: Dict):
    platform = (job.get("platform") or "").lower()
    affiliate = build_affiliate_link(platform, job.get("url") or "")

    text = (
        f"🚀 New Opportunity: {job.get('title')}\n"
        f"🌍 Country: {job.get('country') or 'ANY'}\n"
        f"🧭 Platform: {platform.title() if platform else 'N/A'}\n"
        f"🔗 Link: {affiliate}"
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⭐ Keep", callback_data=f"save:{job['id']}"),
            InlineKeyboardButton("🙈 Dismiss", callback_data=f"dismiss:{job['id']}"),
        ],
        [
            InlineKeyboardButton(
                "✍️ Proposal",
                callback_data=f"proposal:{job['id']}|{platform}|{affiliate}|{quote_plus(job.get('title') or '')}"
            ),
            InlineKeyboardButton("🌐 Open", url=affiliate),
        ]
    ])
    if bot:
        bot.send_message(chat_id=uid, text=text, reply_markup=kb)

# ==============================================================================
# MAIN LOOP
# ==============================================================================
def process_user(db, user: User):
    uid = user.telegram_id
    rows = db.query(Keyword).filter_by(user_id=user.id).all()
    keywords = [k.keyword for k in rows]
    logger.info(f"Scanning user={uid} keywords={keywords or ['<none>']} countries={user.countries or 'ALL'}")

    if not keywords:
        return

    sent_this_loop = 0
    dedup_ids: Set[str] = set()  # cross-keyword dedup in this loop

    for kw in keywords:
        try:
            items = fetch_jobs(kw, user.countries)
        except Exception as e:
            logger.exception(f"fetch_jobs failed for user={uid}, keyword='{kw}': {e}")
            continue

        logger.info(f"user={uid} keyword='{kw}' -> {len(items)} jobs")

        for job in items:
            if sent_this_loop >= MAX_SEND_PER_LOOP:
                logger.info(f"user={uid} reached MAX_SEND_PER_LOOP={MAX_SEND_PER_LOOP}. throttling.")
                return

            jid = job.get("id")
            if not jid or jid in dedup_ids:
                continue
            dedup_ids.add(jid)

            # per-user persisted dedup
            if db.query(JobSent).filter_by(user_id=user.id, job_id=jid).first():
                logger.debug(f"user={uid} job_id={jid} already sent; skip")
                continue

            try:
                send_job(uid, job)
                sent_this_loop += 1
                logger.info(f"sent job_id={jid} to user={uid} (platform={job.get('platform')}, country={job.get('country')})")
            except Exception as te:
                logger.exception(f"Telegram send failed user={uid} job_id={jid}: {te}")
                continue

            try:
                db.add(JobSent(user_id=user.id, job_id=jid))
                db.commit()
                logger.debug(f"marked job_id={jid} as sent for user={uid}")
            except Exception as se:
                db.rollback()
                logger.exception(f"DB commit failed user={uid} job_id={jid}: {se}")

def run_worker():
    logger.info(
        f"Worker start :: DEBUG={DEBUG} MOCK_JOBS={MOCK_JOBS} INTERVAL={WORKER_INTERVAL}s | "
        f"SOURCES: FL={FREELANCER_ENABLED} ROK={REMOTEOK_ENABLED} WWR={WWR_ENABLED} RMT={REMOTIVE_ENABLED} | "
        f"FILTERS: MAX_AGE_MIN={MAX_AGE_MIN} MIN_BUDGET={MIN_BUDGET} HOURLY=[{MIN_HOURLY},{MAX_HOURLY or '∞'}] TYPES={','.join(INCLUDE_TYPES) if INCLUDE_TYPES else 'ANY'} | "
        f"REQ_SKILLS={','.join(REQUIRED_SKILLS) if REQUIRED_SKILLS else '-'} EXC_SKILLS={','.join(EXCLUDED_SKILLS) if EXCLUDED_SKILLS else '-'}"
    )
    while True:
        t0 = time.time()
        try:
            db = SessionLocal()
            users = db.query(User).all()
            logger.info(f"Loaded {len(users)} users from DB")
            for user in users:
                try:
                    process_user(db, user)
                except Exception as ue:
                    logger.exception(f"Unhandled error processing user={user.telegram_id}: {ue}")
        except Exception as e:
            logger.exception(f"Top-level loop error: {e}")
        finally:
            try:
                db.close()
            except Exception:
                pass

        elapsed = time.time() - t0
        sleep_for = max(1, WORKER_INTERVAL - int(elapsed))
        logger.debug(f"Loop took {elapsed:.2f}s, sleeping {sleep_for}s")
        time.sleep(sleep_for)

if __name__ == "__main__":
    try:
        run_worker()
    except KeyboardInterrupt:
        logger.info("Worker stopped.")
