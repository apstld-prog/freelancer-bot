import asyncio
import os
import logging
import httpx
from datetime import datetime, timezone

from db import get_session, User, Job, now_utc
from utils import send_telegram_message, convert_to_usd

logger = logging.getLogger("db")
logger.setLevel(logging.INFO)

# ───────────────────────────────────────────────
# 🔤 English → Greek keyword translation layer
# ───────────────────────────────────────────────
EN_GR_TRANSLATIONS = {
    "lighting": ["φωτισμός", "φωτιστικά", "φως"],
    "led": ["led", "λεντ", "φωτιστικά led"],
    "design": ["σχεδίαση", "μελέτη", "σχεδιασμός"],
    "light": ["φως", "φωτισμός"],
    "logo": ["λογότυπο", "λογο", "brand"],
    "photometric": ["φωτοτεχνία", "φωτοτεχνικός", "φωτομετρία"],
    "dialux": ["dialux", "ντιαλαξ"],
    "relux": ["relux", "ριλαξ"],
    "engineer": ["μηχανικός", "σχεδιαστής"],
    "project": ["έργο", "μελέτη", "πρότζεκτ"],
    "architecture": ["αρχιτεκτονική", "αρχιτέκτονας"],
    "render": ["απόδοση", "visualization", "3d"],
    "animation": ["κινούμενα σχέδια", "animation", "γραφικά"],
    "marketing": ["μάρκετινγκ", "προώθηση", "διαφήμιση"],
    "copywriting": ["κειμενογράφηση", "άρθρα", "κειμενογράφος"],
}

# ───────────────────────────────────────────────
# Helper functions
# ───────────────────────────────────────────────
async def fetch_json(url):
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()

def expand_keywords(keywords):
    expanded = set()
    for kw in keywords:
        expanded.add(kw)
        if kw.lower() in EN_GR_TRANSLATIONS:
            expanded.update(EN_GR_TRANSLATIONS[kw.lower()])
    return list(expanded)

# ───────────────────────────────────────────────
# Job fetchers
# ───────────────────────────────────────────────
async def fetch_freelancer(keyword):
    url = f"https://www.freelancer.com/api/projects/0.1/projects/active/?query={keyword}&limit=30&compact=true&user_details=true&job_details=true&full_description=true"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        if r.status_code != 200:
            logger.warning(f"Freelancer fetch error for '{keyword}': {r.status_code}")
            return []
        data = r.json()
        projects = data.get("result", {}).get("projects", [])
        jobs = []
        for p in projects:
            title = p.get("title", "No title")
            desc = p.get("preview_description", "")
            budget = p.get("budget", {})
            min_b = budget.get("minimum", 0)
            max_b = budget.get("maximum", 0)
            currency = budget.get("currency", {}).get("code", "USD")
            usd_budget = convert_to_usd(min_b, max_b, currency)
            link = f"https://www.freelancer.com/projects/{p.get('seo_url')}"
            jobs.append({
                "title": title,
                "description": desc,
                "budget": usd_budget,
                "url": link,
                "source": "Freelancer",
            })
        logger.info(f"Freelancer '{keyword}': {len(jobs)} jobs")
        return jobs

async def fetch_pph(keyword):
    try:
        url = f"https://www.peopleperhour.com/freelance-jobs?q={keyword}"
        async with httpx.AsyncClient() as client:
            r = await client.get(url)
            if r.status_code != 200:
                logger.warning(f"PPH fetch error for '{keyword}': {r.status_code}")
                return []
            # προσωρινό placeholder γιατί δεν έχει API
            return []
    except Exception as e:
        logger.error(f"PPH fetch failed for '{keyword}': {e}")
        return []

async def fetch_kariera(keyword):
    url = f"https://www.kariera.gr/jobs?keyword={keyword}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        if r.status_code != 200:
            logger.warning(f"Kariera fetch error for '{keyword}': {r.status_code}")
            return []
        # Placeholder parsing
        return []
        
# ───────────────────────────────────────────────
# Main worker logic
# ───────────────────────────────────────────────
async def process_user(db, user: User):
    now = now_utc()
    if user.is_blocked:
        return 0
    trial = user.trial_until
    access = user.access_until
    if trial and trial < now and (not access or access < now):
        return 0

    keywords = [k.keyword for k in user.keywords]
    if not keywords:
        return 0

    expanded_keywords = expand_keywords(keywords)

    all_jobs = []
    for kw in expanded_keywords:
        f_jobs = await fetch_freelancer(kw)
        p_jobs = await fetch_pph(kw)
        k_jobs = await fetch_kariera(kw)
        all_jobs.extend(f_jobs + p_jobs + k_jobs)

    sent = 0
    for job in all_jobs:
        exists = db.query(Job).filter_by(url=job["url"], user_id=user.id).first()
        if exists:
            continue

        msg = (
            f"💼 *{job['title']}*\n"
            f"💰 Budget: {job['budget']}\n"
            f"🌐 Source: {job['source']}\n\n"
            f"{job['description']}\n\n"
            f"🔗 [View Job]({job['url']})"
        )
        await send_telegram_message(user.telegram_id, msg)
        db.add(Job(user_id=user.id, url=job["url"], title=job["title"]))
        db.commit()
        sent += 1

    logger.info(f"Worker sent {sent} jobs to {user.telegram_id}")
    return sent

# ───────────────────────────────────────────────
# Worker loop
# ───────────────────────────────────────────────
async def worker_loop():
    while True:
        try:
            with get_session() as db:
                users = db.query(User).all()
                total = 0
                for u in users:
                    total += await process_user(db, u)
                logger.info(f"Worker cycle complete. Sent {total} messages.")
        except Exception as e:
            logger.exception(f"Worker loop error: {e}")
        await asyncio.sleep(300)

if __name__ == "__main__":
    asyncio.run(worker_loop())
