# worker.py
# -*- coding: utf-8 -*-
"""
Background worker:
- Διαβάζει keywords χρηστών από DB
- Τραβά αγγελίες από πηγές (με Skywalker RSS ενσωματωμένο)
- Dedup (με προτεραιότητα affiliate)
- Στέλνει μηνύματα στο Telegram και καταγράφει JobSent για /feedstats

Σημειώσεις:
- Δεν αλλάζει το "στήσιμο": παραμένει ξεχωριστός worker (start_worker.sh).
- Έχουμε safety γύρω από optional imports: αν κάποια πηγή δεν υπάρχει, απλώς παραλείπεται.
- Skywalker RSS: feeds.skywalker_feed.fetch_skywalker_feed(base_keywords)
"""

from __future__ import annotations

import os
import re
import asyncio
import logging
from typing import List, Dict, Optional, Callable
from datetime import datetime, timedelta, timezone

import httpx

# -------------------- Logging --------------------
log = logging.getLogger("worker")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

# -------------------- Config / ENV --------------------
try:
    # Προσπαθούμε να φέρουμε flags/affiliates αν έχεις config.py
    from config import (
        ENABLE_FREELANCER, ENABLE_PPH, ENABLE_KARIERA, ENABLE_JOBFIND,
        ENABLE_SKYWALKER, ENABLE_CAREERJET,
        ENABLE_MALT, ENABLE_WORKANA, ENABLE_TWAGO, ENABLE_FREELANCERMAP,
        ENABLE_YUNOJUNO, ENABLE_WORKSOME, ENABLE_CODEABLE, ENABLE_GURU,
        ENABLE_99DESIGNS, ENABLE_WRIPPLE, ENABLE_TOPTAL,
        PPH_AFFILIATE_BASE,
        ADMIN_STATS_NOTIFY,
    )
except Exception:
    # Sensible defaults
    ENABLE_FREELANCER = True
    ENABLE_PPH = True
    ENABLE_KARIERA = True
    ENABLE_JOBFIND = True
    ENABLE_SKYWALKER = True
    ENABLE_CAREERJET = True
    ENABLE_MALT = True
    ENABLE_WORKANA = True
    ENABLE_TWAGO = True
    ENABLE_FREELANCERMAP = True
    ENABLE_YUNOJUNO = True
    ENABLE_WORKSOME = True
    ENABLE_CODEABLE = True
    ENABLE_GURU = True
    ENABLE_99DESIGNS = True
    ENABLE_WRIPPLE = True
    ENABLE_TOPTAL = True
    PPH_AFFILIATE_BASE = os.getenv("PPH_AFFILIATE_BASE", "").strip()
    ADMIN_STATS_NOTIFY = (os.getenv("ADMIN_STATS_NOTIFY", "false").lower() == "true")

BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
if not BOT_TOKEN:
    log.warning("BOT_TOKEN missing; Telegram sends will be skipped.")

HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "20"))
CYCLE_SECONDS = int(os.getenv("CYCLE_SECONDS", "300"))  # default 5'
DEDUP_WINDOW_HOURS = int(os.getenv("DEDUP_WINDOW_HOURS", "72"))

# -------------------- DB models --------------------
SessionLocal = None
User = None
Keyword = None
JobSent = None

try:
    from db import SessionLocal as _SessionLocal, User as _User, Keyword as _Keyword, JobSent as _JobSent
    SessionLocal = _SessionLocal
    User = _User
    Keyword = _Keyword
    JobSent = _JobSent
except Exception as e:
    log.warning("DB imports not available (%s) — running in no-DB mode.", e)

# -------------------- Sources: Skywalker RSS --------------------
# Ο fetcher είναι από το αρχείο feeds/skywalker_feed.py
try:
    from feeds.skywalker_feed import fetch_skywalker_feed
    HAS_SKY = True
except Exception as e:
    log.warning("Skywalker feed module not found (%s).", e)
    HAS_SKY = False

# -------------------- Optional: Other sources (best-effort) --------------------
# Αν έχεις υλοποιήσει αντίστοιχες συναρτήσεις, θα κληθούν.
def _optional_source_call(name: str, func: Callable, *args, **kwargs) -> List[Dict]:
    try:
        return asyncio.get_event_loop().run_until_complete(func(*args, **kwargs))  # unlikely path; we use await elsewhere
    except RuntimeError:
        # If already in async loop (normal), use it properly
        pass
    return []

# -------------------- Helpers --------------------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _normalize_text(s: str) -> str:
    try:
        import unicodedata
        s = (s or "").lower()
        s = unicodedata.normalize("NFD", s)
        s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
        s = re.sub(r"[^a-z0-9\u0370-\u03FF]+", " ", s)
        return re.sub(r"\s+", " ", s).strip()
    except Exception:
        return (s or "").lower().strip()

def job_card_with_match(card: Dict, match_kw: str) -> Dict:
    c = dict(card)
    c["match_kw"] = match_kw
    return c

def is_affiliate(card: Dict) -> bool:
    pu = (card.get("proposal_url") or "").lower()
    ou = (card.get("original_url") or "").lower()
    if pu and ou and pu != ou:
        return True
    aff_hints = ["awinaffid=", "awinmid=", "clickref=", "ref=", "partner=", "utm_source=", "aff"]
    return any(h in pu for h in aff_hints)

def dedup_cards(cards: List[Dict]) -> List[Dict]:
    """
    Dedup by normalized title+source; prefer affiliate.
    """
    def key_for(c: Dict) -> str:
        title = _normalize_text(c.get("title", ""))
        src = c.get("source", "")
        return f"{src}|{title}"

    chosen: Dict[str, Dict] = {}
    for c in cards:
        k = key_for(c)
        prev = chosen.get(k)
        if not prev:
            chosen[k] = c
            continue
        # Score: affiliate wins; else keep first
        score = (1 if is_affiliate(c) else 0) - (1 if is_affiliate(prev) else 0)
        if score > 0:
            chosen[k] = c
    return list(chosen.values())

# -------------------- Telegram send --------------------
async def send_telegram(chat_id: int, text: str, buttons: Optional[List[List[Dict]]] = None):
    """
    Στέλνει μήνυμα μέσω Telegram Bot API (χωρίς python-telegram-bot εδώ).
    """
    if not BOT_TOKEN:
        log.info("Skip send (no BOT_TOKEN): %s", text[:120])
        return
    api = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if buttons:
        # buttons: [[{"text": "...", "url": "..."}, ...], ...]
        payload["reply_markup"] = {"inline_keyboard": buttons}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        r = await client.post(api, json=payload)
        if r.status_code != 200:
            log.warning("Telegram send fail [%s]: %s", r.status_code, r.text)

def format_card_to_text(card: Dict) -> (str, List[List[Dict]]):
    title = card.get("title") or "Untitled"
    src = card.get("source") or "?"
    desc = (card.get("description") or "").strip()
    posted = card.get("posted") or "recent"
    budget = card.get("budget_local") or card.get("budget_usd") or "—"
    url = card.get("proposal_url") or card.get("original_url") or ""
    head = f"📌 <b>{title}</b>\n<code>{src}</code> • {posted}\n💰 {budget}"
    body = f"\n\n{desc}" if desc else ""
    text = head + body
    btns = []
    if url:
        btns = [[{"text": "🔗 Άνοιγμα", "url": url}]]
    return text, btns

# -------------------- DB helpers --------------------
def db_available() -> bool:
    return SessionLocal is not None and User is not None and Keyword is not None and JobSent is not None

def iter_users_and_keywords():
    """
    Επιστρέφει [(user, [keywords...]), ...]
    """
    if not db_available():
        return []
    db = SessionLocal()
    users_out = []
    try:
        users = db.query(User).all()
        for u in users:
            # find telegram/chat id
            chat_id = None
            for f in ("chat_id", "telegram_id", "tg_id", "user_id"):
                if hasattr(u, f):
                    chat_id = getattr(u, f)
                    try:
                        chat_id = int(chat_id)
                    except Exception:
                        pass
                    break
            # list keywords
            kws: List[str] = []
            # via relationship
            if hasattr(u, "keywords") and getattr(u, "keywords") is not None:
                try:
                    for k in getattr(u, "keywords"):
                        for fld in ("text", "name", "word", "value", "keyword"):
                            if hasattr(k, fld):
                                v = getattr(k, fld)
                                if v:
                                    kws.append(str(v))
                                break
                except Exception:
                    pass
            # fallback query
            if not kws:
                try:
                    q = db.query(Keyword)
                    uid = None
                    for uf in ("id", "user_id", "pk"):
                        if hasattr(u, uf):
                            uid = getattr(u, uf)
                            break
                    if uid is not None:
                        for kf in ("user_id", "uid", "owner_id"):
                            if hasattr(Keyword, kf):
                                q = q.filter(getattr(Keyword, kf) == uid)
                                break
                        rows = q.all()
                        for k in rows:
                            for fld in ("text", "name", "word", "value", "keyword"):
                                if hasattr(k, fld):
                                    v = getattr(k, fld)
                                    if v:
                                        kws.append(str(v))
                                    break
                except Exception:
                    pass

            users_out.append((u, chat_id, kws))
    finally:
        db.close()
    return users_out

def was_sent_recently(db, job_id: str, user) -> bool:
    """
    Έλεγξε αν έχει σταλεί το συγκεκριμένο job_id στον χρήστη εντός DEDUP_WINDOW_HOURS.
    """
    since = now_utc() - timedelta(hours=DEDUP_WINDOW_HOURS)
    q = db.query(JobSent).filter(JobSent.created_at >= since)
    # Αν το JobSent έχει πεδία user_id/chat_id, τα χρησιμοποιούμε:
    if hasattr(JobSent, "user_id"):
        uid = None
        for uf in ("id", "user_id", "pk"):
            if hasattr(user, uf):
                uid = getattr(user, uf); break
        if uid is not None:
            q = q.filter(JobSent.user_id == uid)
    if hasattr(JobSent, "chat_id"):
        chat = None
        for f in ("chat_id", "telegram_id", "tg_id", "user_id"):
            if hasattr(user, f):
                chat = getattr(user, f); break
        if chat is not None:
            q = q.filter(JobSent.chat_id == chat)
    q = q.filter(JobSent.job_id == job_id)
    return q.first() is not None

def record_sent(db, job_id: str, user, source: str):
    row = JobSent()
    # try set user/chat identifiers if fields exist
    for uf in ("user_id", "uid", "owner_id"):
        if hasattr(JobSent, uf):
            # must set from user
            val = None
            for f in ("id", "user_id", "pk", "telegram_id", "chat_id", "tg_id"):
                if hasattr(user, f):
                    val = getattr(user, f); break
            if val is not None:
                setattr(row, uf, val)
    if hasattr(JobSent, "chat_id"):
        for f in ("chat_id", "telegram_id", "tg_id", "user_id"):
            if hasattr(user, f):
                setattr(row, "chat_id", getattr(user, f))
                break
    if hasattr(JobSent, "job_id"):
        setattr(row, "job_id", job_id)
    if hasattr(JobSent, "source"):
        setattr(row, "source", source)
    if hasattr(JobSent, "created_at"):
        setattr(row, "created_at", now_utc())
    db.add(row)
    db.commit()

# -------------------- Collectors --------------------

async def collect_skywalker(base_keywords: List[str]) -> List[Dict]:
    if not ENABLE_SKYWALKER or not HAS_SKY:
        return []
    try:
        cards = await fetch_skywalker_feed(base_keywords)
        log.info("Skywalker: %d candidates", len(cards))
        return cards
    except Exception as e:
        log.exception("Skywalker error: %s", e)
        return []

# Stubs for other sources (αν υπάρχουν υλοποιημένα κάπου αλλού, μπορείς να τα καλέσεις εδώ)
async def collect_other_sources(base_keywords: List[str]) -> List[Dict]:
    all_cards: List[Dict] = []

    # Παράδειγμα για Freelancer API, αν υπάρχει συνάρτηση get_freelancer_cards(...)
    try:
        if ENABLE_FREELANCER:
            from sources.freelancer import search_freelancer_cards  # π.χ. δικό σου module
            for kw in base_keywords:
                try:
                    items = await search_freelancer_cards(kw)
                    for c in items:
                        all_cards.append(job_card_with_match(c, kw))
                except Exception as e:
                    log.exception("Freelancer fetch failed (%s): %s", kw, e)
    except Exception:
        pass

    # Παράδειγμα για PPH
    try:
        if ENABLE_PPH:
            from sources.pph import search_pph_cards
            for kw in base_keywords:
                try:
                    items = await search_pph_cards(kw, affiliate_base=PPH_AFFILIATE_BASE)
                    for c in items:
                        all_cards.append(job_card_with_match(c, kw))
                except Exception as e:
                    log.exception("PPH fetch failed (%s): %s", kw, e)
    except Exception:
        pass

    # Αντίστοιχα μπορείς να προσθέσεις Kariera, JobFind, Careerjet, κτλ
    # ... (κρατάω το αρχείο καθαρό — οι υλοποιήσεις σου παραμένουν όπως ήταν)

    return all_cards

# -------------------- Main loop --------------------

async def worker_cycle():
    """
    Ένας κύκλος: διαβάζει users/keywords, μαζεύει αγγελίες, κάνει dedup,
    και στέλνει σε κάθε χρήστη ό,τι δεν έχει σταλεί πρόσφατα.
    """
    users = iter_users_and_keywords()
    if not users:
        log.info("No users in DB or DB unavailable.")
        return

    # Συλλογή από όλες τις πηγές (μία φορά ανά κύκλο)
    # 1) Skywalker (RSS)
    cards_sky = await collect_skywalker(base_keywords=_collect_global_keywords(users))
    # 2) Άλλες πηγές (ό,τι έχεις υλοποιήσει)
    cards_other = await collect_other_sources(base_keywords=_collect_global_keywords(users))

    all_cards = []
    for c in cards_sky:
        all_cards.append(job_card_with_match(c, c.get("title", "")))
    for c in cards_other:
        all_cards.append(c)

    # Dedup
    all_cards = dedup_cards(all_cards)

    if not db_available():
        # Χωρίς DB δεν μπορούμε να ξέρουμε αν έχει σταλεί ήδη — απλώς log
        log.info("DB unavailable — %d cards collected (no sends).", len(all_cards))
        return

    # Στείλε σε κάθε χρήστη ανάλογα με τα keywords του
    sent_total = 0
    db = SessionLocal()
    try:
        for user, chat_id, kws in users:
            if not chat_id:
                continue
            # φιλτράρισμα για τον συγκεκριμένο user
            user_cards = _filter_cards_for_user(all_cards, kws)
            for card in user_cards:
                jid = card.get("id") or ""
                src = card.get("source") or "?"
                if not jid:
                    continue
                if was_sent_recently(db, jid, user):
                    continue
                text, btns = format_card_to_text(card)
                await send_telegram(chat_id, text, btns)
                record_sent(db, jid, user, src)
                sent_total += 1
    finally:
        db.close()

    log.info("Worker cycle complete. Sent %d messages.", sent_total)

    # Προαιρετικό admin notify ανά κύκλο
    if ADMIN_STATS_NOTIFY and BOT_TOKEN:
        try:
            admin_id = int(os.getenv("ADMIN_ID", "0"))
        except Exception:
            admin_id = 0
        if admin_id:
            await send_telegram(admin_id, f"📊 Worker cycle done. Sent: {sent_total}")

def _collect_global_keywords(users_bundle) -> List[str]:
    """
    Παίρνει όλες τις λέξεις από όλους τους χρήστες (unique, normalized).
    """
    allk = []
    seen = set()
    for _user, _chat, kws in users_bundle:
        for w in kws:
            w = (w or "").strip()
            if not w:
                continue
            n = _normalize_text(w)
            if n and n not in seen:
                seen.add(n)
                allk.append(w)  # κρατάμε και την αρχική μορφή (ο skywalker fetcher κάνει tonos-insensitive)
    return allk

def _filter_cards_for_user(cards: List[Dict], user_keywords: List[str]) -> List[Dict]:
    if not user_keywords:
        return []
    res = []
    # κάνε απλό contains στο normalized title/desc
    kws_norm = [_normalize_text(k) for k in user_keywords if k]
    for c in cards:
        hay = _normalize_text(f"{c.get('title','')} {c.get('description','')}")
        if any(kn and kn in hay for kn in kws_norm):
            res.append(c)
    return res

# -------------------- Entrypoint --------------------

async def worker_loop():
    log.info("Worker started. Cycle every %ss", CYCLE_SECONDS)
    while True:
        try:
            await worker_cycle()
        except Exception as e:
            log.exception("Worker cycle error: %s", e)
        await asyncio.sleep(CYCLE_SECONDS)

def main():
    asyncio.run(worker_loop())

if __name__ == "__main__":
    main()
