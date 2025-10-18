#!/usr/bin/env python3
# worker_runner.py — Merge Freelancer + PeoplePerHour, 48h freshness, keyword filter, chronological sort
import os, logging, asyncio, hashlib
from typing import Dict, List, Optional, Set
from datetime import datetime, timezone, timedelta
from html import escape as _esc

from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
log = logging.getLogger("worker")
FRESH_HOURS = int(os.getenv("FRESH_WINDOW_HOURS", "48"))

from sqlalchemy import text as _sql_text
from db import get_session as _get_session
from db_keywords import list_keywords as _list_keywords

def _ensure_sent_schema():
    with _get_session() as s:
        s.execute(_sql_text("""
            CREATE TABLE IF NOT EXISTS sent_job (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                job_key TEXT NOT NULL,
                sent_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC'),
                UNIQUE (user_id, job_key)
            )
        """)); s.commit()

def _already_sent(user_id: int, job_key: str) -> bool:
    _ensure_sent_schema()
    with _get_session() as s:
        row = s.execute(_sql_text("SELECT 1 FROM sent_job WHERE user_id=:u AND job_key=:k LIMIT 1"), {"u": user_id, "k": job_key}).fetchone()
        return row is not None

def _mark_sent(user_id: int, job_key: str) -> None:
    with _get_session() as s:
        s.execute(_sql_text("INSERT INTO sent_job (user_id, job_key) VALUES (:u, :k) ON CONFLICT DO NOTHING"), {"u": user_id, "k": job_key}); s.commit()

def _fetch_all_users() -> List[int]:
    ids: Set[int] = set()
    with _get_session() as s:
        rows = s.execute(_sql_text('SELECT DISTINCT telegram_id FROM "user" WHERE telegram_id IS NOT NULL AND COALESCE(is_blocked,false)=false AND COALESCE(is_active,true)=true')).fetchall()
        ids.update(int(r[0]) for r in rows if r[0] is not None)
    return sorted(list(ids))

def _fetch_user_keywords(telegram_id: int) -> List[str]:
    try:
        with _get_session() as s:
            row = s.execute(_sql_text('SELECT id FROM "user" WHERE telegram_id=:tid'), {"tid": telegram_id}).fetchone()
            if not row: return []
            uid = int(row[0])
        kws = _list_keywords(uid) or []
        return [k.strip() for k in kws if k and k.strip()]
    except Exception:
        return []

def _h(s: str) -> str:
    return _esc((s or '').strip(), quote=False)

def _to_dt(val):
    if val is None: return None
    try:
        if isinstance(val,(int,float)):
            sec=float(val); 
            if sec>1e12: sec/=1000.0
            return datetime.fromtimestamp(sec,tz=timezone.utc)
        s=str(val).strip()
        if s.isdigit():
            sec=int(s); 
            if sec>1e12: sec/=1000.0
            return datetime.fromtimestamp(sec,tz=timezone.utc)
        s2=s.replace("Z","+00:00")
        for fmt in ("%Y-%m-%dT%H:%M:%S%z","%Y-%m-%d %H:%M:%S%z","%Y-%m-%dT%H:%M:%S.%f%z","%Y-%m-%d %H:%M:%S","%Y-%m-%dT%H:%M:%S","%a, %d %b %Y %H:%M:%S %z"):
            try:
                dt=datetime.strptime(s2,fmt)
                return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
            except Exception: pass
    except Exception: return None
    return None

def _extract_dt(it: Dict):
    for k in ("time_submitted","posted_at","created_at","timestamp","date","pub_date","published"):
        dt=_to_dt(it.get(k))
        if dt: return dt
    return None

def _compose_message(it: Dict) -> str:
    title=(it.get("title") or "").strip() or "Untitled"
    desc=(it.get("description") or "").strip()
    if len(desc)>700: desc=desc[:700]+"…"
    src=(it.get("source") or "Freelancer").strip() or "Freelancer"
    display_ccy = it.get("currency_display") or it.get("budget_currency") or it.get("original_currency") or it.get("currency_code_detected") or it.get("currency") or "USD"
    budget_min=it.get("budget_min"); budget_max=it.get("budget_max")
    usd_min=it.get("budget_min_usd"); usd_max=it.get("budget_max_usd")
    def _fmt(v):
        try: f=float(v); s=f"{f:.1f}"; return s.rstrip("0").rstrip(".")
        except Exception: return str(v)
    orig=""
    if budget_min is not None and budget_max is not None: orig=f"{_fmt(budget_min)}–{_fmt(budget_max)} {display_ccy}"
    elif budget_min is not None: orig=f"from {_fmt(budget_min)} {display_ccy}"
    elif budget_max is not None: orig=f"up to {_fmt(budget_max)} {display_ccy}"
    usd_hint=""
    if usd_min is not None and usd_max is not None: usd_hint=f" (~${_fmt(usd_min)}–${_fmt(usd_max)} USD)"
    elif usd_min is not None: usd_hint=f" (~${_fmt(usd_min)} USD)"
    elif usd_max is not None: usd_hint=f" (~${_fmt(usd_max)} USD)"
    lines=[f"<b>{_h(title)}</b>"]
    if orig or usd_hint: lines.append(f"<b>Budget:</b> {_h((orig+usd_hint).strip())}")
    lines.append(f"<b>Source:</b> {_h(src)}")
    dt=_extract_dt(it)
    if dt:
        now=datetime.now(timezone.utc); diff=now-dt; minutes=int(diff.total_seconds()//60)
        if minutes<1: rel="just now"
        elif minutes<60: rel=f"{minutes} minute{'s' if minutes!=1 else ''} ago"
        else:
            hours=minutes//60
            rel=f"{hours} hour{'s' if hours!=1 else ''} ago" if hours<24 else f"{hours//24} day{'s' if hours//24!=1 else ''} ago"
        lines.append(f"<b>Posted:</b> {rel}")
    mk=it.get("matched_keyword") or it.get("match") or it.get("keyword")
    if mk: lines.append(f"<b>Match:</b> {_h(mk)}")
    if desc: lines.append(_h(desc))
    return "\n".join(lines)

def _build_keyboard(links: Dict[str, Optional[str]]):
    row1 = [InlineKeyboardButton("📄 Proposal", url=(links.get("proposal") or links.get("original") or "")),
            InlineKeyboardButton("🔗 Original", url=(links.get("original") or ""))]
    row2 = [InlineKeyboardButton("⭐ Save", callback_data="job:save"),
            InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")]
    return InlineKeyboardMarkup([row1,row2])

def _resolve_links(it: Dict) -> Dict[str, Optional[str]]:
    original = it.get("original_url") or it.get("url") or ""
    proposal = it.get("proposal_url") or original or ""
    return {"original": original, "proposal": proposal}

def _job_key(it: Dict) -> str:
    base = (it.get("url") or it.get("original_url") or "").strip() or f"{it.get('source','')}::{(it.get('title') or '')[:160]}"
    return hashlib.sha1(base.encode("utf-8","ignore")).hexdigest()

def _gather_items(keywords: List[str]) -> List[Dict]:
    out: List[Dict] = []
    try:
        import platform_freelancer as pf
        its = pf.get_items(keywords)
        for it in its: it.setdefault("source","freelancer")
        out.extend(its)
    except Exception as e:
        log.warning("freelancer fetch failed: %s", e)
    try:
        if os.getenv("ENABLE_PPH","0")=="1" and os.getenv("P_PEOPLEPERHOUR","0")=="1":
            import platform_peopleperhour as pph
            its = pph.get_items(keywords)
            for it in its: it.setdefault("source","peopleperhour")
            out.extend(its)
    except Exception as e:
        log.warning("pph fetch failed: %s", e)
    return out

async def _send_items(bot: Bot, chat_id: int, items: List[Dict], per_user_batch: int):
    sent=0
    for it in items:
        if sent>=per_user_batch: break
        key=_job_key(it)
        if _already_sent(chat_id,key): continue
        try:
            await bot.send_message(chat_id=chat_id, text=_compose_message(it), parse_mode=ParseMode.HTML,
                                   reply_markup=_build_keyboard(_resolve_links(it)), disable_web_page_preview=True)
            _mark_sent(chat_id,key); sent+=1; await asyncio.sleep(0.35)
        except Exception as e:
            log.warning("send_message failed: %s", e)

def _cutoff(): return datetime.now(timezone.utc) - timedelta(hours=FRESH_HOURS)

def _kw_match(it: Dict, kws: List[str]):
    hay=f"{(it.get('title') or '').lower()}\n{(it.get('description') or '').lower()}"
    for kw in kws or []:
        k=(kw or '').strip().lower()
        if k and k in hay: return kw
    return None

async def amain():
    token=os.getenv("TELEGRAM_BOT_TOKEN","") or os.getenv("BOT_TOKEN","" )
    if not token: raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")
    interval=int(os.getenv("WORKER_INTERVAL","120")); per_user_batch=int(os.getenv("BATCH_PER_TICK","5"))
    bot=Bot(token=token)

    users=[]
    with _get_session() as s:
        rows=s.execute(_sql_text('SELECT DISTINCT telegram_id FROM "user" WHERE telegram_id IS NOT NULL AND COALESCE(is_blocked,false)=false AND COALESCE(is_active,true)=true')).fetchall()
        users=[int(r[0]) for r in rows]

    while True:
        try:
            cutoff=_cutoff()
            for tid in users:
                kws=_fetch_user_keywords(tid)
                items=_gather_items(kws)

                filtered=[]
                for it in items:
                    mk=it.get("matched_keyword") or _kw_match(it,kws)
                    if kws and not mk: continue
                    if mk: it["matched_keyword"]=mk
                    dt=_extract_dt(it)
                    if not dt or dt<cutoff: continue
                    filtered.append(it)

                filtered.sort(key=lambda x: _extract_dt(x) or cutoff, reverse=True)
                if filtered:
                    await _send_items(bot, tid, filtered, per_user_batch)
        except Exception as e:
            log.error("[runner] error: %s", e)
        await asyncio.sleep(interval)

if __name__ == "__main__":
    asyncio.run(amain())
