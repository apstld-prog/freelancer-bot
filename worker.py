import os
import logging
from typing import List, Dict, Tuple
from datetime import timedelta

import httpx

from db import get_session, now_utc, User, Keyword, Job, JobSent, SavedJob

# ----------------------------------------------------------------------------
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("db")

INTERVAL_SEC = int(os.getenv("WORKER_INTERVAL", "120"))
ENABLE_FREELANCER = True
ENABLE_PPH = os.getenv("ENABLE_PPH", "1") == "1"
ENABLE_KARIERA = os.getenv("ENABLE_KARIERA", "1") == "1"
ENABLE_JOBFIND = os.getenv("ENABLE_JOBFIND", "0") == "1"  # currently off (404 endpoints)

# New stubs
ENABLE_TWAGO         = os.getenv("ENABLE_TWAGO", "0") == "1"
ENABLE_FREELANCERMAP = os.getenv("ENABLE_FREELANCERMAP", "0") == "1"
ENABLE_YUNOJUNO      = os.getenv("ENABLE_YUNOJUNO", "0") == "1"
ENABLE_WORKSOME      = os.getenv("ENABLE_WORKSOME", "0") == "1"
ENABLE_CODEABLE      = os.getenv("ENABLE_CODEABLE", "0") == "1"
ENABLE_GURU          = os.getenv("ENABLE_GURU", "0") == "1"
ENABLE_99DESIGNS     = os.getenv("ENABLE_99DESIGNS", "0") == "1"

AFFILIATE_FREELANCER_REF = os.getenv("AFFILIATE_FREELANCER_REF", "")
USD_SYMBOLS = {"$", "USD", "usd", "US$", "us$"}

# simple EN→GR mapping for Greek boards
EN_GR_MAP = {
    "lighting": ["φωτισ", "φωτοτεχν", "φωτομετρ"],
    "led": ["led"],
    "logo": ["λογοτυπ"],
    "luminaire": ["φωτιστικ", "σώμα φωτισμ"],
    "photometric": ["φωτομετρ"],
    "dialux": ["dialux"],
    "relux": ["relux"],
}

# ----------------------------------------------------------------------------

def usd_convert(amount: float, currency: str) -> Tuple[str, float]:
    # simple static rates; replace with live if later
    rates = {"EUR": 1.08, "USD": 1.0, "GBP": 1.25}
    cur = currency or "USD"
    rate = rates.get(cur.upper())
    if not rate or not amount:
        return cur.upper(), amount
    return "USD", round(amount * rate, 2)

def make_card_text(job: Job, matched: str) -> str:
    budget_line = ""
    if job.budget_min or job.budget_max:
        rng = f"{job.budget_min or ''}–{job.budget_max or ''} {job.budget_currency or ''}".strip("– ").strip()
        usd_line = ""
        cur = job.budget_currency or ""
        if cur.upper() != "USD":
            low = job.budget_min or 0
            high = job.budget_max or 0
            if low:
                _, low_usd = usd_convert(low, cur)
            else:
                low_usd = 0
            if high:
                _, high_usd = usd_convert(high, cur)
            else:
                high_usd = 0
            if low_usd or high_usd:
                usd_line = f"\n~ ${low_usd:.0f}–${high_usd:.0f} USD"
        budget_line = f"\n💲 Budget: {rng}{usd_line}"
    bids = f"\n👥 Bids: {job.bids}" if job.bids is not None else ""
    return (
        f"*{job.title}*\n\n"
        f"Source: *{job.source.capitalize()}*\n"
        f"Type: Fixed"
        f"{budget_line}{bids}\n"
        f"Posted: recent\n\n"
        f"Matched: {matched}"
    )

def job_card_with_match(j: Dict, match_kw: str) -> Dict:
    return {**j, "_matched": match_kw}

# ----------------------------------------------------------------------------
# Fetchers
# ----------------------------------------------------------------------------

async def freelancer_search(client: httpx.AsyncClient, kw: str) -> List[Dict]:
    url = ("https://www.freelancer.com/api/projects/0.1/projects/active/"
           f"?query={httpx.QueryParams({'query': kw})['query']}&limit=30&compact=true&user_details=true&job_details=true&full_description=true")
    r = await client.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    out = []
    for p in data.get("result", {}).get("projects", []):
        jid = str(p["id"])
        title = p.get("title") or "(no title)"
        url_job = f"https://www.freelancer.com/projects/{jid}"
        prop, orig = affiliate_wrap("freelancer", url_job)
        out.append({
            "source": "freelancer",
            "external_id": jid,
            "title": title,
            "url": url_job,
            "proposal_url": prop,
            "original_url": orig,
            "budget_min": p.get("budget", {}).get("minimum"),
            "budget_max": p.get("budget", {}).get("maximum"),
            "budget_currency": p.get("currency", {}).get("code"),
            "bids": p.get("bid_stats", {}).get("bid_count"),
            "description": (p.get("preview_description") or "")[:1000],
        })
    log.info("Freelancer '%s': %d jobs", kw, len(out))
    return out

async def pph_search(client: httpx.AsyncClient, kw: str) -> List[Dict]:
    # simple HTML search (results limited)
    url = f"https://www.peopleperhour.com/freelance-jobs?q={kw}"
    r = await client.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        log.info("PPH '%s': 0 jobs (status %s)", kw, r.status_code)
        return []
    # Keep as a stubbed zero until we add HTML parser for items
    log.info("PPH '%s': 0 jobs", kw)
    return []

async def kariera_search(client: httpx.AsyncClient, kw: str) -> List[Dict]:
    url = f"https://www.kariera.gr/jobs?keyword={kw}"
    r = await client.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        log.info("Kariera '%s': 0 jobs (status %s)", kw, r.status_code)
        return []
    # Lightweight, no scrape of each listing; we return 0 until solid parser is added
    log.info("Kariera '%s': 0 jobs (post-filtered)", kw)
    return []

# Stubs for new platforms
async def twago_search(kw: str) -> List[Dict]:
    log.info("twago '%s': stub active", kw); return []
async def freelancermap_search(kw: str) -> List[Dict]:
    log.info("freelancermap '%s': stub active", kw); return []
async def yuno_juno_search(kw: str) -> List[Dict]:
    log.info("YunoJuno '%s': stub active", kw); return []
async def worksome_search(kw: str) -> List[Dict]:
    log.info("Worksome '%s': stub active", kw); return []
async def codeable_search(kw: str) -> List[Dict]:
    log.info("Codeable '%s': stub active", kw); return []
async def guru_search(kw: str) -> List[Dict]:
    log.info("Guru '%s': stub active", kw); return []
async def ninetyninedesigns_search(kw: str) -> List[Dict]:
    log.info("99designs '%s': stub active", kw); return []

def affiliate_wrap(source: str, url: str) -> Tuple[str, str]:
    if source == "freelancer" and AFFILIATE_FREELANCER_REF:
        sep = "&" if "?" in url else "?"
        w = f"{url}{sep}referrer={AFFILIATE_FREELANCER_REF}"
        return w, w
    return url, url

# ----------------------------------------------------------------------------
# Worker loop
# ----------------------------------------------------------------------------

async def process_user(db, u: User) -> int:
    sent = 0
    if not u.is_active():
        return sent

    # build keywords EN + GR mirrors
    kws_en = []
    kws_gr = []
    for k in [x.keyword for x in u.keywords]:
        if any(ord(c) > 127 for c in k):
            kws_gr.append(k)
            # map to possible EN seeds
            for en, grs in EN_GR_MAP.items():
                if any(part in k for part in grs):
                    kws_en.append(en)
        else:
            kws_en.append(k)
            # back-map to GR for greek boards
            for en, grs in EN_GR_MAP.items():
                if en in k:
                    kws_gr.extend(grs)

    kws_en = sorted(set(kws_en))
    kws_gr = sorted(set(kws_gr))

    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        cards: List[Dict] = []

        if ENABLE_FREELANCER:
            for kw in kws_en:
                try:
                    for c in await freelancer_search(client, kw):
                        cards.append(job_card_with_match(c, kw))
                except Exception as e:
                    log.warning("Freelancer fetch error for '%s': %s", kw, e)

        if ENABLE_PPH:
            for kw in kws_en:
                try:
                    for c in await pph_search(client, kw):
                        cards.append(job_card_with_match(c, kw))
                except Exception as e:
                    log.warning("PPH fetch error for '%s': %s", kw, e)

        if ENABLE_KARIERA and kws_gr:
            for kw in kws_gr:
                try:
                    for c in await kariera_search(client, kw):
                        cards.append(job_card_with_match(c, kw))
                except Exception as e:
                    log.warning("Kariera fetch error for '%s': %s", kw, e)

        # new stubs (safe)
        for kw in kws_en:
            if ENABLE_TWAGO: cards += [*await twago_search(kw)]
            if ENABLE_FREELANCERMAP: cards += [*await freelancermap_search(kw)]
            if ENABLE_YUNOJUNO: cards += [*await yuno_juno_search(kw)]
            if ENABLE_WORKSOME: cards += [*await worksome_search(kw)]
            if ENABLE_CODEABLE: cards += [*await codeable_search(kw)]
            if ENABLE_GURU: cards += [*await guru_search(kw)]
            if ENABLE_99DESIGNS: cards += [*await ninetyninedesigns_search(kw)]

    # deduplicate by source/external_id and send
    total = 0
    for c in cards:
        job = db.query(Job).filter(Job.source==c["source"], Job.external_id==c["external_id"]).one_or_none()
        if not job:
            job = Job(**{k: c.get(k) for k in [
                "source","external_id","title","url","proposal_url","original_url",
                "budget_min","budget_max","budget_currency","bids","description"
            ]})
            db.add(job); db.commit()
        # check sent
        already = db.query(JobSent).filter(JobSent.user_id==u.id, JobSent.job_id==job.id).one_or_none()
        if already: continue

        text = make_card_text(job, c.get("_matched",""))
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Proposal", url=job.proposal_url or job.url),
             InlineKeyboardButton("🔗 Original", url=job.original_url or job.url)],
            [InlineKeyboardButton("⭐ Keep", callback_data=f"keep:{job.id}"),
             InlineKeyboardButton("🗑️ Delete", callback_data=f"del:{job.id}")]
        ])

        try:
            from telegram import Bot
            bot = Bot(os.getenv("BOT_TOKEN",""))
            bot.send_message  # type: ignore
            # use async
        except Exception:
            pass

        # use PTB-less direct API via httpx (async)
        api = f"https://api.telegram.org/bot{os.getenv('BOT_TOKEN','')}/sendMessage"
        payload = {
            "chat_id": int(u.telegram_id),
            "text": text,
            "parse_mode": "Markdown",
            "reply_markup": kb.to_json()
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(api, json=payload, timeout=30)
            r.raise_for_status()

        db.add(JobSent(user_id=u.id, job_id=job.id)); db.commit()
        total += 1

    return total

async def worker_loop():
    log.info("Worker loop every %ss (JOB_MATCH_SCOPE=title_desc)", INTERVAL_SEC)
    while True:
        try:
            db = get_session()
            users = db.query(User).all()
            total_sent = 0
            for u in users:
                try:
                    total_sent += await process_user(db, u)
                except Exception as e:
                    log.exception("process_user error for %s: %s", u.telegram_id, e)
            log.info("Worker cycle complete. Sent %d messages.", total_sent)
        except Exception as e:
            log.exception("Worker loop error: %s", e)
        finally:
            try: db.close()
            except: pass
        import asyncio
        await asyncio.sleep(INTERVAL_SEC)

if __name__ == "__main__":
    import asyncio
    asyncio.run(worker_loop())
