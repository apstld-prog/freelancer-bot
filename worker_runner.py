#!/usr/bin/env python3
# Unified worker runner (Freelancer + PPH + Greek feeds)
import os, asyncio, hashlib, logging, time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode

from sqlalchemy import text as _sql
from db import get_session as _get_session
from db_keywords import list_keywords as _list_keywords

# --- import platform fetchers (leave unchanged names) ---
from platform_freelancer import fetch_freelancer_jobs
from platform_peopleperhour import fetch_pph_jobs
from platform_skywalker import fetch_skywalker_jobs

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
log = logging.getLogger("worker")

# Intervals (env) — keep UI unchanged
WORKER_INTERVAL      = int(os.getenv("WORKER_INTERVAL", "180"))
FREELANCER_INTERVAL  = int(os.getenv("FREELANCER_INTERVAL", "60"))
PPH_INTERVAL         = int(os.getenv("PPH_INTERVAL", "300"))
GREEK_INTERVAL       = int(os.getenv("GREEK_INTERVAL", "300"))
FRESH_HOURS          = int(os.getenv("FRESH_WINDOW_HOURS", "48"))

DEFAULT_URLS = {
    "freelancer":   "https://www.freelancer.com/",
    "peopleperhour":"https://www.peopleperhour.com/",
    "skywalker":    "https://www.skywalker.gr/jobs/",
    "generic":      "https://www.google.com/",
}

# -------------- DB helpers (de-dup per user) --------------
def _ensure_sent_schema():
    with _get_session() as s:
        s.execute(_sql("""
            CREATE TABLE IF NOT EXISTS sent_job (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                job_key TEXT NOT NULL,
                sent_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC'),
                UNIQUE (user_id, job_key)
            )
        """))
        s.commit()

def _already_sent(user_id: int, job_key: str) -> bool:
    _ensure_sent_schema()
    with _get_session() as s:
        row = s.execute(_sql(
            "SELECT 1 FROM sent_job WHERE user_id=:u AND job_key=:k LIMIT 1"
        ), {"u": user_id, "k": job_key}).fetchone()
        return row is not None

def _mark_sent(user_id: int, job_key: str) -> None:
    with _get_session() as s:
        s.execute(_sql(
            "INSERT INTO sent_job (user_id, job_key) VALUES (:u, :k) ON CONFLICT DO NOTHING"
        ), {"u": user_id, "k": job_key})
        s.commit()

def _fetch_all_users() -> List[int]:
    ids = []
    with _get_session() as s:
        rows = s.execute(_sql(
            'SELECT DISTINCT telegram_id FROM "user" '
            'WHERE telegram_id IS NOT NULL AND COALESCE(is_blocked,false)=false AND COALESCE(is_active,true)=true'
        )).fetchall()
        ids = [int(r[0]) for r in rows if r[0] is not None]
    return sorted(ids)

def _fetch_user_keywords(tid: int) -> List[str]:
    try:
        with _get_session() as s:
            row = s.execute(_sql('SELECT id FROM "user" WHERE telegram_id=:tid'), {"tid": tid}).fetchone()
            if not row: return []
            uid = int(row[0])
        kws = _list_keywords(uid) or []
        return [k.strip() for k in kws if k and k.strip()]
    except Exception:
        return []

# -------------- utils --------------
def _job_key(it: Dict) -> str:
    base = (it.get("original_url") or it.get("url") or it.get("title") or "").strip()
    src  = (it.get("source") or "").strip()
    key_data = f"{src}|{base}"
    return hashlib.sha1(key_data.encode("utf-8","ignore")).hexdigest()

def _to_dt(val) -> Optional[datetime]:
    if val is None: return None
    try:
        if isinstance(val, (int, float)):
            sec = float(val)
            if sec > 1e12: sec /= 1000.0
            return datetime.fromtimestamp(sec, tz=timezone.utc)
        s = str(val).strip()
        if s.isdigit():
            sec = int(s)
            if sec > 1e12: sec /= 1000.0
            return datetime.fromtimestamp(sec, tz=timezone.utc)
    except Exception:
        return None
    return None

def _time_ago(dt: datetime) -> str:
    now = datetime.now(timezone.utc); delta = now - dt
    s = int(max(0, delta.total_seconds()))
    if s < 60: return "just now"
    m = s // 60
    if m < 60: return f"{m} minute{'s' if m!=1 else ''} ago"
    h = m // 60
    if h < 24: return f"{h} hour{'s' if h!=1 else ''} ago"
    d = h // 24
    return f"{d} day{'s' if d!=1 else ''} ago"

def _compose_message(it: Dict) -> str:
    title = (it.get("title") or "Untitled").strip()
    desc  = (it.get("description") or "").strip()
    src   = (it.get("source") or "Freelancer").strip()
    kw    = (it.get("matched_keyword") or "").strip()

    bmin, bmax = it.get("budget_min"), it.get("budget_max")
    ccy = it.get("budget_currency") or it.get("currency") or it.get("currency_code_detected") or "USD"

    def _fmt(v):
        try:
            f=float(v); s=f"{f:.1f}"
            return s.rstrip("0").rstrip(".")
        except Exception:
            return str(v) if v is not None else ""

    budget_line = ""
    if bmin is not None and bmax is not None:
        budget_line = f"{_fmt(bmin)}–{_fmt(bmax)} {ccy}"
    elif bmin is not None:
        budget_line = f"from {_fmt(bmin)} {ccy}"
    elif bmax is not None:
        budget_line = f"up to {_fmt(bmax)} {ccy}"

    lines = [f"<b>{title}</b>"]
    if budget_line:
        lines.append(f"<b>Budget:</b> {budget_line}")
    lines.append(f"<b>Source:</b> {src}")
    if kw:
        lines.append(f"<b>Match:</b> {kw}")

    if desc:
        if len(desc) > 700: desc = desc[:700] + "…"
        lines.append(f"📝 {desc}")

    dt = _to_dt(it.get("time_submitted"))
    if dt:
        lines.append(f"<i>{_time_ago(dt)}</i>")
    return "\n".join(lines)

def _safe_default_url(source: str) -> str:
    s = (source or "").lower()
    if "peopleperhour" in s: return DEFAULT_URLS["peopleperhour"]
    if "skywalker" in s:     return DEFAULT_URLS["skywalker"]
    if "freelancer" in s:    return DEFAULT_URLS["freelancer"]
    return DEFAULT_URLS["generic"]

def _build_keyboard(it: Dict) -> InlineKeyboardMarkup:
    # NEVER send an empty url button to Telegram
    src = it.get("source") or ""
    proposal = (it.get("proposal_url") or "").strip()
    original = (it.get("original_url") or "").strip()
    affiliate = (it.get("affiliate_url") or "").strip()
    safe = _safe_default_url(src)

    url1 = proposal or affiliate or original or safe
    url2 = original or affiliate or proposal or safe
    if not (url1.startswith("http")): url1 = safe
    if not (url2.startswith("http")): url2 = safe

    row1 = [
        InlineKeyboardButton("📄 Proposal", url=url1),
        InlineKeyboardButton("🔗 Original",  url=url2),
    ]
    row2 = [
        InlineKeyboardButton("⭐ Save",   callback_data="job:save"),
        InlineKeyboardButton("🗑️ Delete", callback_data="job:delete"),
    ]
    return InlineKeyboardMarkup([row1, row2])

# -------------- fetch orchestrator --------------
_last_run = {"freelancer":0, "pph":0, "greek":0}

async def gather_items(keywords: List[str]) -> List[Dict]:
    now = time.time()
    items: List[Dict] = []

    if now - _last_run["freelancer"] >= FREELANCER_INTERVAL:
        try:
            fj = fetch_freelancer_jobs(keywords)
            for it in fj: it["source"] = it.get("source") or "Freelancer"
            items.extend(fj)
            log.info("[Freelancer] fetched %d items", len(fj))
        except Exception as e:
            log.warning("Freelancer fetch error: %s", e)
        _last_run["freelancer"] = now

    if now - _last_run["pph"] >= PPH_INTERVAL:
        try:
            pj = fetch_pph_jobs(keywords)
            for it in pj: it["source"] = it.get("source") or "PeoplePerHour"
            items.extend(pj)
            log.info("[PPH] fetched %d items", len(pj))
        except Exception as e:
            log.warning("PPH fetch error: %s", e)
        _last_run["pph"] = now

    if now - _last_run["greek"] >= GREEK_INTERVAL:
        try:
            sj = fetch_skywalker_jobs(keywords)
            for it in sj: it["source"] = it.get("source") or "Skywalker"
            items.extend(sj)
            log.info("[Skywalker] fetched %d items", len(sj))
        except Exception as e:
            log.warning("Skywalker fetch error: %s", e)
        _last_run["greek"] = now

    return items

# -------------- sender --------------
async def send_items(bot: Bot, chat_id: int, jobs: List[Dict], per_user_batch: int):
    sent = 0
    for it in jobs:
        if sent >= per_user_batch: break
        key = _job_key(it)
        if _already_sent(chat_id, key): 
            continue
        try:
            msg = _compose_message(it)
            kb  = _build_keyboard(it)
            await bot.send_message(chat_id=chat_id, text=msg,
                                   parse_mode=ParseMode.HTML,
                                   reply_markup=kb,
                                   disable_web_page_preview=True)
            _mark_sent(chat_id, key)
            sent += 1
            await asyncio.sleep(0.35)
        except Exception as e:
            log.warning("send_message failed for %s: %s", chat_id, e)
    if sent:
        srcs = { (it.get('source') or '').lower() for it in jobs[:sent] }
        log.info("Sent %d jobs → %s (sources=%s)", sent, chat_id, ",".join(sorted(srcs)))

# -------------- main loop --------------
async def amain():
    token = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or ""
    if not token:
        raise RuntimeError("BOT_TOKEN/TELEGRAM_BOT_TOKEN missing")

    bot = Bot(token=token)
    users = _fetch_all_users()
    per_user_batch = int(os.getenv("BATCH_PER_TICK", "5"))
    cutoff = lambda: datetime.now(timezone.utc) - timedelta(hours=FRESH_HOURS)

    log.info("🚀 Starting unified worker (Freelancer + PPH + Greek feeds)")
    while True:
        try:
            for tid in users:
                kws = _fetch_user_keywords(tid)
                items = await gather_items(kws)

                # filter by keywords and freshness
                keep: List[Dict] = []
                for it in items:
                    mk = it.get("matched_keyword")
                    if not mk and kws:
                        hay = f"{(it.get('title') or '').lower()}\n{(it.get('description') or '').lower()}"
                        for k in kws:
                            if (k or '').strip().lower() in hay:
                                mk = k; break
                    if kws and not mk:
                        continue
                    if mk: it["matched_keyword"] = mk
                    dt = _to_dt(it.get("time_submitted"))
                    if not dt or dt < cutoff():
                        continue
                    keep.append(it)

                keep.sort(key=lambda x: _to_dt(x.get("time_submitted")) or datetime(1970,1,1,tzinfo=timezone.utc), reverse=True)
                if keep:
                    await send_items(bot, tid, keep, per_user_batch)
        except Exception as e:
            log.error("worker loop error: %s", e)

        await asyncio.sleep(WORKER_INTERVAL)

if __name__ == "__main__":
    asyncio.run(amain())
