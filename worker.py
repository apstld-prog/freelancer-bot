import os
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

import httpx
from sqlalchemy.orm import joinedload
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, constants

from db import SessionLocal, User, Keyword, JobSent

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [worker] %(levelname)s: %(message)s")
logger = logging.getLogger("worker")

# ---------------- Config ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is not set.")

# Affiliate / behavior
FREELANCER_REF_CODE = os.getenv("FREELANCER_REF_CODE", "").strip()      # e.g. "apstld"
AFFILIATE_PREFIX    = os.getenv("AFFILIATE_PREFIX", "").strip()

# Search behavior
SEARCH_MODE = os.getenv("SEARCH_MODE", "all").lower()  # "all" or "single"
INTERVAL    = int(os.getenv("WORKER_INTERVAL", "300"))

# Freelancer filters
FL_PROJECT_TYPE = os.getenv("FREELANCER_PROJECT_TYPE", "all").lower()  # "all" | "fixed" | "hourly"
try:
    FL_MIN_BUDGET = float(os.getenv("FREELANCER_MIN_BUDGET", "0") or 0)
except Exception:
    FL_MIN_BUDGET = 0.0
try:
    FL_MAX_BUDGET = float(os.getenv("FREELANCER_MAX_BUDGET", "0") or 0)  # 0 = no cap
except Exception:
    FL_MAX_BUDGET = 0.0

# Fiverr anti-spam mode:
#   off   -> never send Fiverr messages (default)
#   daily -> at most 1 message per keyword per day
FIVERR_MODE         = os.getenv("FIVERR_MODE", "off").lower()
FIVERR_AFF_TEMPLATE = os.getenv("FIVERR_AFF_TEMPLATE", "").strip()

# Telegram bot (reusable)
bot = Bot(BOT_TOKEN)

# ---------------- Helpers ----------------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def user_is_active(u: User) -> bool:
    if getattr(u, "is_blocked", False):
        return False
    t = now_utc()
    if getattr(u, "access_until", None) and u.access_until >= t:
        return True
    if getattr(u, "trial_until", None) and u.trial_until >= t:
        return True
    return False

def affiliate_wrap(url: str) -> str:
    return f"{AFFILIATE_PREFIX}{url}" if AFFILIATE_PREFIX else url

def aff_for_source(source: str, url: str) -> str:
    # Freelancer: append ?f=<code> if provided
    if source == "freelancer" and FREELANCER_REF_CODE and "freelancer.com" in url:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}f={FREELANCER_REF_CODE}"
    # Other sources -> global prefix if any
    return affiliate_wrap(url)

def timeago(ts: Optional[int]) -> str:
    if not ts:
        return "unknown"
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    delta = now_utc() - dt
    secs = int(delta.total_seconds())
    if secs < 60: return f"{secs}s ago"
    mins = secs // 60
    if mins < 60: return f"{mins}m ago"
    hrs = mins // 60
    if hrs < 24: return f"{hrs}h ago"
    days = hrs // 24
    return f"{days}d ago"

def passes_budget(budget: Optional[Dict[str, Any]]) -> bool:
    if not budget:
        return True
    mn = float(budget.get("minimum") or 0)
    mx = float(budget.get("maximum") or 0)
    if FL_MIN_BUDGET and (mx or mn) and (mx < FL_MIN_BUDGET and mn < FL_MIN_BUDGET):
        return False
    if FL_MAX_BUDGET and (mn or mx) and (mn > FL_MAX_BUDGET and mx > FL_MAX_BUDGET):
        return False
    return True

def passes_type(type_str: Optional[str]) -> bool:
    if FL_PROJECT_TYPE == "all":
        return True
    if not type_str:
        return True
    t = type_str.lower()
    if FL_PROJECT_TYPE == "fixed" and "fixed" in t:
        return True
    if FL_PROJECT_TYPE == "hourly" and "hour" in t:
        return True
    return False

def format_budget(budget: Optional[Dict[str, Any]], proj_type: Optional[str]) -> str:
    if not budget:
        return "—"
    cur = (budget.get("currency") or {}).get("code") or ""
    mn = budget.get("minimum")
    mx = budget.get("maximum")
    if proj_type and "hour" in (proj_type or "").lower():
        if mn and mx:
            return f"{mn}–{mx} {cur}/h"
        if mn:
            return f"≥ {mn} {cur}/h"
        if mx:
            return f"≤ {mx} {cur}/h"
        return f"— {cur}/h"
    else:
        if mn and mx:
            return f"{mn}–{mx} {cur}"
        if mn:
            return f"≥ {mn} {cur}"
        if mx:
            return f"≤ {mx} {cur}"
        return f"— {cur}".strip()

# ---------------- Fetchers ----------------
async def fetch_freelancer(keywords: List[str]) -> List[Dict[str, Any]]:
    """Fetch active projects from Freelancer public API using referral code."""
    if not FREELANCER_REF_CODE:
        logger.warning("Freelancer ref code missing, skipping Freelancer API.")
        return []

    base_url = "https://www.freelancer.com/api/projects/0.1/projects/active/"
    queries: List[str] = []

    if not keywords:
        return []

    if SEARCH_MODE == "single":
        queries.extend(keywords)
    else:
        queries.append(",".join(keywords))

    out: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=25) as client:
        for q in queries:
            params = {
                "query": q,
                "limit": 30,
                "compact": "true",
                "user_details": "true",
                "job_details": "true",
                "full_description": "true",
                "referrer": FREELANCER_REF_CODE,
            }
            try:
                r = await client.get(base_url, params=params)
                if r.status_code != 200:
                    logger.warning("Freelancer API non-200 (%s) for query '%s'", r.status_code, q)
                    continue
                data = r.json()
                for pr in data.get("result", {}).get("projects", []):
                    proj_type = pr.get("type") or pr.get("project_type")
                    if not passes_type(proj_type):
                        continue
                    budget = pr.get("budget")
                    if not passes_budget(budget):
                        continue

                    pid = pr.get("id")
                    url = f"https://www.freelancer.com/projects/{pid}"
                    title = pr.get("title") or "Untitled"
                    desc = pr.get("preview_description") or pr.get("description") or ""
                    bids = pr.get("bid_count") or (pr.get("bid_stats") or {}).get("bid_count")
                    created_ts = pr.get("time_submitted") or pr.get("submitdate")

                    out.append({
                        "id": f"freelancer-{pid}",
                        "title": title,
                        "description": desc,
                        "url": url,
                        "source": "freelancer",
                        "budget": budget,
                        "proj_type": proj_type,
                        "bids": bids,
                        "created_ts": created_ts,
                    })
            except Exception as e:
                logger.warning("Error fetching Freelancer API for '%s': %s", q, e)
    return out

async def fetch_fiverr(keywords: List[str]) -> List[Dict[str, Any]]:
    """
    Fiverr muted by default to avoid spam.
    If FIVERR_MODE == 'daily' and FIVERR_AFF_TEMPLATE provided,
    send at most one reminder per keyword per day (not "jobs", just a curated link).
    """
    if FIVERR_MODE not in ("daily",):
        # Completely off (default)
        return []

    if not FIVERR_AFF_TEMPLATE:
        logger.info("Fiverr mode is daily but template missing; skipping.")
        return []

    # Build one synthetic "job" per keyword per day (dedupe via JobSent)
    today = datetime.utcnow().strftime("%Y%m%d")
    out: List[Dict[str, Any]] = []
    for kw in keywords:
        url = FIVERR_AFF_TEMPLATE.replace("{kw}", kw)
        out.append({
            "id": f"fiverr-{kw}-{today}",  # stable id once per day per keyword (anti-spam)
            "title": f"Fiverr services for {kw}",
            "description": f"Browse Fiverr gigs related to '{kw}'.",
            "url": url,
            "source": "fiverr",
            "budget": None,
            "proj_type": None,
            "bids": None,
            "created_ts": int(now_utc().timestamp()),
        })
    return out

# ---------------- Sending ----------------
async def send_job_to_user(u: User, job: Dict[str, Any]) -> None:
    src = job.get("source", "")
    proj_type = job.get("proj_type") or ""
    budget = format_budget(job.get("budget"), proj_type)
    bids = job.get("bids")
    created = timeago(job.get("created_ts"))

    meta_lines = [f"👤 Source: *{src.capitalize()}*"]
    if proj_type:
        pretty_type = "Hourly" if "hour" in proj_type.lower() else "Fixed"
        meta_lines.append(f"🧾 Type: *{pretty_type}*")
    meta_lines.append(f"💰 Budget: *{budget}*")
    if bids is not None:
        meta_lines.append(f"📨 Bids: *{bids}*")
    if created:
        meta_lines.append(f"🕒 Posted: *{created}*")
    meta = "\n".join(meta_lines)

    text_desc = (job.get("description") or "").strip()
    if len(text_desc) > 700:
        text_desc = text_desc[:700] + "…"

    title = job.get("title", "New opportunity")
    final_url = aff_for_source(src, job.get("url", ""))

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💼 Proposal", url=final_url),
         InlineKeyboardButton("🔗 Original", url=final_url)]
    ])

    text = f"💼 *{title}*\n\n{meta}\n\n{text_desc}"
    try:
        await bot.send_message(
            chat_id=u.telegram_id,
            text=text,
            parse_mode=constants.ParseMode.MARKDOWN,
            reply_markup=kb,
            disable_web_page_preview=True,
        )
        logger.info("Sent job %s to %s", job.get("id"), u.telegram_id)
    except Exception as e:
        logger.warning("Error sending job %s to %s: %s", job.get("id"), u.telegram_id, e)

# ---------------- Main loop ----------------
async def worker_cycle():
    db = SessionLocal()
    try:
        users = db.query(User).options(joinedload(User.keywords)).all()
        total_sent = 0
        for u in users:
            if not user_is_active(u):
                continue
            kws = [k.keyword for k in u.keywords]
            if not kws:
                continue

            jobs: List[Dict[str, Any]] = []
            # Main: Freelancer
            jobs.extend(await fetch_freelancer(kws))
            # Optional: Fiverr (anti-spam controlled)
            jobs.extend(await fetch_fiverr(kws))

            # Dedup by job id
            seen = set()
            deduped: List[Dict[str, Any]] = []
            for j in jobs:
                jid = j.get("id")
                if not jid or jid in seen:
                    continue
                seen.add(jid)
                deduped.append(j)

            # Already sent IDs for this user
            sent_ids = {row.job_id for row in db.query(JobSent).filter_by(user_id=u.id).all()}

            for job in deduped:
                jid = job.get("id")
                if not jid or jid in sent_ids:
                    continue
                # Mark as sent (JobSent has only user_id, job_id)
                db.add(JobSent(user_id=u.id, job_id=jid))
                db.commit()

                await send_job_to_user(u, job)
                total_sent += 1

        logger.info("Worker cycle complete. Sent %d messages.", total_sent)
    except Exception as e:
        logger.exception("Worker cycle error: %s", e)
    finally:
        db.close()

async def worker_loop():
    logger.info("Worker loop every %ss (SEARCH_MODE=%s, FL_TYPE=%s, MIN=%s, MAX=%s, FIVERR_MODE=%s)",
                INTERVAL, SEARCH_MODE, FL_PROJECT_TYPE, FL_MIN_BUDGET, FL_MAX_BUDGET, FIVERR_MODE)
    while True:
        await worker_cycle()
        await asyncio.sleep(INTERVAL)

if __name__ == "__main__":
    asyncio.run(worker_loop())
