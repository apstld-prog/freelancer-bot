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
from currency_usd import usd_line  # ✅ Added for currency conversion

# --- import platform fetchers ---
from platform_freelancer import fetch_freelancer_jobs
from platform_peopleperhour import fetch_pph_jobs
from platform_skywalker import fetch_skywalker_jobs

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
log = logging.getLogger("worker")

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

# ---------------- DB helpers ----------------
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

def _mark_sent(user_id: int, job_key: str):
    with _get_session() as s:
        s.execute(_sql(
            "INSERT INTO sent_job (user_id, job_key) VALUES (:u, :k) ON CONFLICT DO NOTHING"
        ), {"u": user_id, "k": job_key})
        s.commit()

def _fetch_all_users() -> List[int]:
    with _get_session() as s:
        rows = s.execute(_sql(
            'SELECT DISTINCT telegram_id FROM "user" '
            'WHERE telegram_id IS NOT NULL AND COALESCE(is_blocked,false)=false AND COALESCE(is_active,true)=true'
        )).fetchall()
        return [int(r[0]) for r in rows if r[0]]

def _fetch_user_keywords(tid: int) -> List[str]:
    try:
        with _get_session() as s:
            row = s.execute(_sql('SELECT id FROM "user" WHERE telegram_id=:tid'), {"tid": tid}).fetchone()
            if not row: return []
            uid = int(row[0])
        kws = _list_keywords(uid) or []
        return [k.strip() for k in kws if k.strip()]
    except Exception:
        return []

# ---------------- Utils ----------------
def _job_key(it: Dict) -> str:
    base = (it.get("original_url") or it.get("url") or it.get("title") or "").strip()
    src  = (it.get("source") or "").strip()
    return hashlib.sha1(f"{src}|{base}".encode("utf-8","ignore")).hexdigest()

def _to_dt(val) -> Optional[datetime]:
    if not val: return None
    try:
        if isinstance(val, (int, float)):
            if val > 1e12: val /= 1000
            return datetime.fromtimestamp(val, tz=timezone.utc)
        s = str(val).strip()
        if s.isdigit():
            sec = int(s)
            if sec > 1e12: sec /= 1000
            return datetime.fromtimestamp(sec, tz=timezone.utc)
    except Exception:
        return None
    return None

def _time_ago(dt: datetime) -> str:
    delta = datetime.now(timezone.utc) - dt
    s = int(max(0, delta.total_seconds()))
    if s < 60: return "just now"
    m = s // 60
    if m < 60: return f"{m} minute{'s' if m!=1 else ''} ago"
    h = m // 60
    if h < 24: return f"{h} hour{'s' if h!=1 else ''} ago"
    d = h // 24
    return f"{d} day{'s' if d!=1 else ''} ago"

def _safe_default_url(source: str) -> str:
    s = (source or "").lower()
    if "peopleperhour" in s: return DEFAULT_URLS["peopleperhour"]
    if "skywalker" in s:     return DEFAULT_URLS["skywalker"]
    if "freelancer" in s:    return DEFAULT_URLS["freelancer"]
    return DEFAULT_URLS["generic"]

def _build_keyboard(it: Dict) -> InlineKeyboardMarkup:
    src = it.get("source") or ""
    proposal = (it.get("proposal_url") or "").strip()
    original = (it.get("original_url") or "").strip()
    affiliate = (it.get("affiliate_url") or "").strip()
    safe = _safe_default_url(src)

    url1 = proposal or affiliate or original or safe
    url2 = original or affiliate or proposal or safe
    if not url1.startswith("http"): url1 = safe
    if not url2.startswith("http"): url2 = safe

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📄 Proposal", url=url1),
            InlineKeyboardButton("🔗 Original", url=url2)
        ],
        [
            InlineKeyboardButton("⭐ Save", callback_data="job:save"),
            InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")
        ]
    ])

def _compose_message(it: Dict) -> str:
    title = (it.get("title") or "Untitled").strip()
    desc = (it.get("description") or "").strip()
    src = (it.get("source") or "Freelancer").strip()
    kw = (it.get("matched_keyword") or "").strip()

    bmin, bmax = it.get("budget_min"), it.get("budget_max")
    ccy = it.get("budget_currency") or "USD"

    budget_line = ""
    if bmin and bmax:
        budget_line = f"{bmin}–{bmax} {ccy}"
    elif bmin:
        budget_line = f"from {bmin} {ccy}"
    elif bmax:
        budget_line = f"up to {bmax} {ccy}"

    # ✅ Add USD equivalent if available
    usd_equiv = usd_line(bmin, bmax, ccy)
    if usd_equiv:
        if budget_line:
            budget_line = f"{budget_line} ({usd_equiv})"
        else:
            budget_line = usd_equiv

    lines = [f"<b>{title}</b>"]
    if budget_line:
        lines.append(f"<b>Budget:</b> {budget_line}")
    lines.append(f"<b>Source:</b> {src}")
    if kw:
        lines.append(f"<b>Match:</b> {kw}")
    if desc:
        if len(desc) > 700:
            desc = desc[:700] + "…"
        lines.append(f"📝 {desc}")
    dt = _to_dt(it.get("time_submitted"))
    if dt:
        lines.append(f"<i>{_time_ago(dt)}</i>")
    return "\n".join(lines)

# ---------------- Main Logic ----------------
_last_run = {"freelancer":0, "pph":0, "greek":0}

# (remaining code unchanged)
