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
<<<<<<< HEAD
    return out
=======
    log.info("Freelancer '%s': %d jobs", keyword, len(cards))
    return cards

# ───────────────────────── PeoplePerHour ─────────────────────────
_PPH_JOB_A = re.compile(r'href="(/job/\d+[^"]+)"[^>]*>([^<]+)</a>', re.IGNORECASE)
_PPH_DATA_ID = re.compile(r'data-job-id="(\d+)"[^>]*>.*?<a[^>]+href="(/job/\d+[^"]+)"[^>]*>([^<]+)</a>', re.IGNORECASE | re.DOTALL)
_PPH_MONEY = re.compile(r'([€£$])\s?(\d+(?:[.,]\d{1,2})?)', re.IGNORECASE)
_PPH_PER_HOUR = re.compile(r'per\s*hour|/hr|/hour', re.IGNORECASE)

def _money_to_code(sym: str) -> str:
    return {"€": "EUR", "£": "GBP", "$": "USD"}.get(sym, "USD")

async def pph_search(keyword: str) -> List[Dict]:
    q = keyword.strip()
    if not q:
        return []
    url = f"https://www.peopleperhour.com/freelance-jobs?q={quote_plus(q)}"
    cards: List[Dict] = []
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=HEADERS_HTML) as client:
            r = await client.get(url)
            if r.status_code != 200:
                log.warning("PPH fetch error for '%s': %s", keyword, r)
                return []
            html = r.text
    except Exception as e:
        log.warning("PPH fetch error for '%s': %s", keyword, e)
        return []

    seen_ids = set()

    def add_pph_card(jid: str, href: str, title: str, context: str):
        nonlocal cards
        if jid in seen_ids:
            return
        seen_ids.add(jid)
        full_url = urljoin("https://www.peopleperhour.com", href)

        minb = maxb = 0.0
        code = "USD"
        ptype = None
        usd_line = None
        local_line = "—"

        money = _PPH_MONEY.search(context)
        if money:
            sym, amt = money.group(1), money.group(2)
            amt_val = float(amt.replace(",", "."))
            code = _money_to_code(sym)
            minb = maxb = amt_val
            ptype = "Hourly" if _PPH_PER_HOUR.search(context) else "Fixed"
            local_line = fmt_local_budget(minb, maxb, code)
            usd_pair = to_usd(minb, maxb, code)
            if usd_pair:
                usd_line = fmt_usd_line(*usd_pair)

        cards.append({
            "id": f"pph-{jid}",
            "source": "PeoplePerHour",
            "title": title or "Untitled",
            "type": ptype,
            "budget_local": local_line,
            "budget_usd": usd_line,
            "bids": None,
            "posted": "recent",
            "description": "",
            "proposal_url": wrap_pph_url(full_url),
            "original_url": wrap_pph_url(full_url),
        })

    for m in _PPH_JOB_A.finditer(html):
        href = m.group(1)
        title = re.sub(r"\s+", " ", m.group(2)).strip()
        jid_m = re.search(r"/job/(\d+)", href)
        if not jid_m:
            continue
        jid = jid_m.group(1)
        start = max(0, m.start() - 300)
        end = min(len(html), m.end() + 300)
        context = html[start:end]
        add_pph_card(jid, href, title, context)

    for m in _PPH_DATA_ID.finditer(html):
        jid = m.group(1)
        href = m.group(2)
        title = re.sub(r"\s+", " ", m.group(3)).strip()
        start = max(0, m.start() - 300)
        end = min(len(html), m.end() + 300)
        context = html[start:end]
        add_pph_card(jid, href, title, context)

    log.info("PPH '%s': %d jobs", keyword, len(cards))
    return cards

# ───────────────────────── 
# ───────────────────────── Skywalker.gr ─────────────────────────
_SKY_A = re.compile(r'href="(/el/aggelia/[^"]+)"[^>]*>([^<]+)</a>', re.IGNORECASE)
async def skywalker_search(keyword_el: str) -> List[Dict]:
    q = keyword_el.strip()
    if not q: return []
    url = f"https://www.skywalker.gr/el/aggelies?keyword={quote_plus(q)}"
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"}) as client:
            r = await client.get(url)
            if r.status_code != 200: return []
            html = r.text
    except Exception: return []
    cards: List[Dict] = []; seen=set()
    for m in _SKY_A.finditer(html):
        href, title = m.group(1), re.sub(r"\s+"," ",m.group(2)).strip()
        full = urljoin("https://www.skywalker.gr", href)
        jid = (re.search(r"/aggelia/(\d+)", href).group(1) if re.search(r"/aggelia/(\d+)", href) else re.sub(r"[^a-zA-Z0-9]","",href)[-16:])
        if jid in seen: continue
        seen.add(jid)
        cards.append({"id": f"sky-{jid}","source":"Skywalker","title":title,"type":None,"budget_local":"—","budget_usd":None,"bids":None,"posted":"recent","description":"","proposal_url":full,"original_url":full})
    return cards

# ───────────────────────── Careerjet.gr ─────────────────────────
_CJ_A = re.compile(r'href="(/jobad/[^"]+)"[^>]*>([^<]+)</a>', re.IGNORECASE)
async def careerjet_search(keyword_el: str) -> List[Dict]:
    q = keyword_el.strip()
    if not q: return []
    url = f"https://www.careerjet.gr/anazitisi/{quote_plus(q)}"
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"}) as client:
            r = await client.get(url)
            if r.status_code != 200: return []
            html = r.text
    except Exception: return []
    cards: List[Dict] = []; seen=set()
    for m in _CJ_A.finditer(html):
        href, title = m.group(1), re.sub(r"\s+"," ",m.group(2)).strip()
        full = urljoin("https://www.careerjet.gr", href)
        jid = re.sub(r"[^a-zA-Z0-9]","",href)[-16:]
        if jid in seen: continue
        seen.add(jid)
        cards.append({"id": f"careerjet-{jid}","source":"Careerjet","title":title or "Untitled","type":None,"budget_local":"—","budget_usd":None,"bids":None,"posted":"recent","description":"","proposal_url":full,"original_url":full})
    return cards
Kariera ─────────────────────────
_KAR_A = re.compile(r'href="(/jobs/[^"]+)"[^>]*>([^<]+)</a>', re.IGNORECASE)

async def kariera_search(keyword_el: str, greek_all_keywords: List[str]) -> List[Dict]:
    q = keyword_el.strip()
    if not q:
        return []
    url = f"https://www.kariera.gr/jobs?keyword={quote_plus(q)}"
    cards: List[Dict] = []
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=HEADERS_HTML) as client:
            r = await client.get(url)
            if r.status_code != 200:
                log.warning("Kariera fetch error for '%s': %s", keyword_el, r)
                return []
            html = r.text
    except Exception as e:
        log.warning("Kariera fetch error for '%s': %s", keyword_el, e)
        return []

    seen = set()
    for m in _KAR_A.finditer(html):
        href = m.group(1)
        title = re.sub(r"\s+", " ", m.group(2)).strip()
        if not title_matches(title, greek_all_keywords, greek_mode=True):
            continue
        jid = re.sub(r"[^a-zA-Z0-9]+", "-", href).strip("-")
        if jid in seen:
            continue
        seen.add(jid)
        full = urljoin("https://www.kariera.gr", href)
        cards.append({
            "id": f"kariera-{jid}",
            "source": "Kariera",
            "title": title or "Untitled",
            "type": None,
            "budget_local": "—",
            "budget_usd": None,
            "bids": None,
            "posted": "recent",
            "description": "",
            "proposal_url": full,
            "original_url": full,
        })
    log.info("Kariera '%s': %d jobs (post-filtered)", keyword_el, len(cards))
    return cards[:MAX_PER_SOURCE]

# ───────────────────────── JobFind ─────────────────────────
_JF_A = re.compile(r'href="(/job/[^"]+)"[^>]*>([^<]+)</a>', re.IGNORECASE)

async def _jobfind_fetch_html(keyword_el: str) -> Optional[str]:
    q = quote_plus(keyword_el.strip())
    candidates = [
        f"https://www.jobfind.gr/ergasia?keyword={q}",
        f"https://www.jobfind.gr/ergasia?keywords={q}",
        f"https://www.jobfind.gr/ergasia/search?keyword={q}",
        f"https://www.jobfind.gr/ergasia/el/search?keyword={q}",
    ]
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=HEADERS_HTML) as client:
        for url in candidates:
            try:
                r = await client.get(url)
                if r.status_code == 200 and r.text:
                    return r.text
                else:
                    log.info("JobFind probe %s → %s", url, r.status_code)
            except Exception as e:
                log.info("JobFind probe error %s → %s", url, e)
    return None

async def jobfind_search(keyword_el: str, greek_all_keywords: List[str]) -> List[Dict]:
    if not keyword_el.strip():
        return []
    html = await _jobfind_fetch_html(keyword_el)
    if not html:
        log.warning("JobFind fetch error for '%s': no working endpoint (404/redirects)", keyword_el)
        return []

    cards: List[Dict] = []
    seen = set()
    for m in _JF_A.finditer(html):
        href = m.group(1)
        title = re.sub(r"\s+", " ", m.group(2)).strip()
        if not title_matches(title, greek_all_keywords, greek_mode=True):
            continue
        jid = re.sub(r"[^a-zA-Z0-9]+", "-", href).strip("-")
        if jid in seen:
            continue
        seen.add(jid)
        full = urljoin("https://www.jobfind.gr", href)
        cards.append({
            "id": f"jobfind-{jid}",
            "source": "JobFind",
            "title": title or "Untitled",
            "type": None,
            "budget_local": "—",
            "budget_usd": None,
            "bids": None,
            "posted": "recent",
            "description": "",
            "proposal_url": full,
            "original_url": full,
        })
    log.info("JobFind '%s': %d jobs (post-filtered)", keyword_el, len(cards))
    return cards[:MAX_PER_SOURCE]

# ───────────────────────── Match & dedup ─────────────────────────
def job_matches(card: Dict, keywords: List[str]) -> bool:
    if not keywords:
        return True

    src = (card.get("source") or "").lower()
    is_gr = src in {"kariera", "jobfind"}

    hay_parts = []
    if JOB_MATCH_SCOPE in ("title", "title_desc"):
        hay_parts.append(card.get("title") or "")
    if JOB_MATCH_SCOPE == "title_desc":
        hay_parts.append(card.get("description") or "")
    hay = " ".join(hay_parts)

    if is_gr:
        hay_norm = normalize_el(hay)
        tokens = [normalize_el(k) for k in keywords if k.strip()]
        if not tokens:
            return True
        if JOB_MATCH_REQUIRE == "all":
            return all(t in hay_norm for t in tokens)
        return any(t in hay_norm for t in tokens)
    else:
        hay_s = hay.lower()
        kws = [k.lower() for k in keywords if k.strip()]
        if not kws:
            return True
        if JOB_MATCH_REQUIRE == "all":
            return all(k in hay_s for k in kws)
        return any(k in hay_s for k in kws)

def dedup_cards(cards: List[Dict]) -> List[Dict]:
    """Deduplicate by normalized title, prefer affiliate sources."""
    def norm_title(t: str) -> str:
        import unicodedata, re as _re
        t = (t or "").lower()
        t = unicodedata.normalize("NFD", t)
        t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
        return _re.sub(r"[^a-z0-9]+", " ", t).strip()
    chosen = {}
    for c in cards:
        key = f"{c.get('source','')}::{norm_title(c.get('title',''))}" or c.get('id')
        prev = chosen.get(key)
        if not prev:
            chosen[key] = c; continue
        def is_aff(card):
            pu=(card.get('proposal_url') or '').lower(); ou=(card.get('original_url') or '').lower()
            if pu!=ou: return True
            return any(x in pu for x in ['?f=','&f=','awinaffid=','awinmid=','clickref=','partner','ref='])
        score = (1 if is_aff(c) else 0) - (1 if is_aff(prev) else 0)
        if score==0:
            hb = bool(c.get('budget_usd') or c.get('budget_local')); pb = bool(prev.get('budget_usd') or prev.get('budget_local'))
            score = (1 if hb else 0) - (1 if pb else 0)
        if score>0: chosen[key]=c
    return list(chosen.values())
>>>>>>> ce3fc6e (Auto commit Tue-10-07 15-23)

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

<<<<<<< HEAD
    return "\n".join([x for x in lines if x is not None])
=======
    if ENABLE_PPH:
        for kw_en in base_keywords:
            try:
                for c in await pph_search(kw_en):
                    all_cards.append(job_card_with_match(c, kw_en))
            except Exception as e:
                log.exception("PPH block error for kw='%s': %s", kw_en, e)

    # 2) Ελληνικές πλατφόρμες → για κάθε αγγλικό, ψάχνουμε με ελληνικές ρίζες
    if ENABLE_KARIERA:
        # Skywalker
        for kw_en in base_keywords:
            for gkw in greek_expansions_for(kw_en):
                try:
                    for c in await skywalker_search(gkw):
                        all_cards.append(job_card_with_match(c, gkw))
                except Exception as e:
                    log.exception("Skywalker block error for kw='%s': %s", gkw, e)
        # Careerjet
        for kw_en in base_keywords:
            for gkw in greek_expansions_for(kw_en):
                try:
                    for c in await careerjet_search(gkw):
                        all_cards.append(job_card_with_match(c, gkw))
                except Exception as e:
                    log.exception("Careerjet block error for kw='%s': %s", gkw, e)
        
        for kw_en in base_keywords:
            greek_keys = greek_expansions_for(kw_en)
            for gkw in greek_keys:
                try:
                    for c in await kariera_search(gkw, greek_keys):
                        all_cards.append(job_card_with_match(c, gkw))  # δείχνει ελληνικό matched
                except Exception as e:
                    log.exception("Kariera block error for gkw='%s': %s", gkw, e)

    if ENABLE_JOBFIND:
        for kw_en in base_keywords:
            greek_keys = greek_expansions_for(kw_en)
            for gkw in greek_keys:
                try:
                    for c in await jobfind_search(gkw, greek_keys):
                        all_cards.append(job_card_with_match(c, gkw))  # ελληνικό matched
                except Exception as e:
                    log.exception("JobFind block error for gkw='%s': %s", gkw, e)

    # Filter & dedup
    filtered: List[Dict] = []
    for c in all_cards:
        src = (c.get("source") or "").lower()
        if src in {"kariera", "jobfind"}:
            keys_for_match = greek_expansions_for(c["matched"][0]) if c.get("matched") else base_keywords
            if not job_matches(c, keys_for_match,):
                continue
        else:
            if not job_matches(c, base_keywords):
                continue
        filtered.append(c)

    filtered = dedup_cards(filtered)

    already = {s.job_id for s in (u.sent_jobs or [])}
    to_send = [c for c in filtered if c.get("id") not in already]
>>>>>>> ce3fc6e (Auto commit Tue-10-07 15-23)

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
