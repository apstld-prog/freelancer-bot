# worker_runner.py
import os, logging, asyncio, hashlib
from typing import Dict, List, Optional, Set
from html import escape as _esc
from datetime import datetime, timezone, timedelta
from currency_usd import usd_line
from worker_stats_sidecar import incr as stats_incr, error as stats_error, publish_stats

import worker as _worker
from sqlalchemy import text as _sql_text
from db import get_session as _get_session
from db_keywords import list_keywords as _list_keywords

from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker_runner")

FRESH_HOURS = int(os.getenv("FRESH_WINDOW_HOURS", "48"))

def _h(s: str) -> str:
    return _esc((s or '').strip(), quote=False)

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
        """))
        s.commit()

def _already_sent(user_id: int, job_key: str) -> bool:
    _ensure_sent_schema()
    with _get_session() as s:
        row = s.execute(_sql_text(
            "SELECT 1 FROM sent_job WHERE user_id=:u AND job_key=:k LIMIT 1"
        ), {"u": user_id, "k": job_key}).fetchone()
        return row is not None

def _mark_sent(user_id: int, job_key: str) -> None:
    with _get_session() as s:
        s.execute(_sql_text(
            "INSERT INTO sent_job (user_id, job_key) VALUES (:u, :k) ON CONFLICT DO NOTHING"
        ), {"u": user_id, "k": job_key})
        s.commit()

def _fetch_all_users() -> List[int]:
    ids: Set[int] = set()
    with _get_session() as s:
        rows = s.execute(_sql_text(
            'SELECT DISTINCT telegram_id, COALESCE(license_until, trial_end) '
            'FROM "user" '
            'WHERE telegram_id IS NOT NULL '
            'AND COALESCE(is_blocked,false)=false '
            'AND COALESCE(is_active,true)=true'
        )).fetchall()

    now = datetime.now(timezone.utc)
    for tid, expiry in rows:
        if tid is None:
            continue
        if expiry is not None:
            # βάλε timezone αν λείπει
            if getattr(expiry, "tzinfo", None) is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry < now:
                # trial/licence έχει λήξει → skip
                continue
        ids.add(int(tid))

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

def _to_dt(val) -> Optional[datetime]:
    if val is None:
        return None
    try:
        if isinstance(val,(int,float)):
            sec=float(val)
            if sec>1e12: sec/=1000.0
            return datetime.fromtimestamp(sec,tz=timezone.utc)
        s=str(val).strip()
        if s.isdigit():
            sec=int(s)
            if sec>1e12: sec/=1000.0
            return datetime.fromtimestamp(sec,tz=timezone.utc)
        s2=s.replace("Z","+00:00")
        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z","%Y-%m-%d %H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z","%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S","%a, %d %b %Y %H:%M:%S %z"
        ):
            try:
                dt=datetime.strptime(s2,fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                return dt
            except Exception:
                pass
    except Exception:
        return None
    return None

def _extract_dt(it: Dict) -> Optional[datetime]:
    for k in ("timestamp","time_submitted","posted_at","created_at","pub_date"):
        dt = _to_dt(it.get(k))
        if dt:
            return dt
    return None

def _compose_message(it: Dict) -> str:
    title = (it.get("title") or "").strip() or "Untitled"
    desc = (it.get("description") or "").strip()
    if len(desc) > 700: desc = desc[:700] + "…"

    src = (it.get("source") or "Freelancer").strip()

    budget_min = it.get("budget_min")
    budget_max = it.get("budget_max")
    currency = it.get("original_currency") or "USD"

    def _fmt(v):
        try:
            f=float(v)
            s=f"{f:.1f}"
            return s.rstrip("0").rstrip(".")
        except:
            return str(v)

            orig = ""
    if budget_min is not None and budget_max is not None:
        orig = f"{_fmt(budget_min)}–{_fmt(budget_max)} {currency}"
    elif budget_min is not None:
        orig = f"from {_fmt(budget_min)} {currency}"
    elif budget_max is not None:
        orig = f"up to {_fmt(budget_max)} {currency}"

    # USD conversion
    usd = None
    try:
        usd = usd_line(budget_min, budget_max, currency)
    except Exception:
        usd = None

    lines = [f"<b>{_h(title)}</b>"]
    if orig:
        if usd:
            lines.append(f"<b>Budget:</b> {_h(orig)} ({_h(usd)})")
        else:
            lines.append(f"<b>Budget:</b> {_h(orig)}")

    lines.append(f"<b>Source:</b> {_h(src)}")

    dt = _extract_dt(it)
    if dt:
        now = datetime.now(timezone.utc)
        diff = now - dt
        mins = int(diff.total_seconds() // 60)
        if mins < 60:
            ago = f"{mins} minutes ago"
        else:
            hrs = mins // 60
            if hrs < 24:
                ago = f"{hrs} hours ago"
            else:
                d = hrs // 24
                ago = f"{d} days ago"
        lines.append(f"<b>Posted:</b> {_h(ago)}")

    mk = it.get("matched_keyword")
    if mk:
        lines.append(f"<b>Match:</b> {_h(mk)}")

    if desc:
        lines.append(_h(desc))

    return "\n".join(lines)

def _job_key(it: Dict) -> str:
    base = (it.get("url") or it.get("original_url") or "").strip()
    if not base:
        base = f"{it.get('source','')}::{(it.get('title') or '')[:200]}"
    return hashlib.sha1(base.encode("utf-8","ignore")).hexdigest()

def _build_keyboard(links: Dict[str, Optional[str]]):
    row1 = [
        InlineKeyboardButton("📄 Proposal", url=(links.get("proposal") or links.get("original") or "")),
        InlineKeyboardButton("🔗 Original", url=(links.get("original") or "")),
    ]
    row2 = [
        InlineKeyboardButton("⭐ Save", callback_data="job:save"),
        InlineKeyboardButton("🗑️ Delete", callback_data="job:delete"),
    ]
    return InlineKeyboardMarkup([row1, row2])

def _resolve_links(it: Dict) -> Dict[str, Optional[str]]:
    original = it.get("url") or it.get("original_url") or ""
    return {
        "original": original,
        "proposal": original,
        "affiliate": original
    }

async def _send_items(bot: Bot, chat_id: int, items: List[Dict], per_user_batch: int):
    sent = 0
    for it in items:
        if sent >= per_user_batch:
            break
        key = _job_key(it)
        if _already_sent(chat_id, key):
            continue
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=_compose_message(it),
                parse_mode=ParseMode.HTML,
                reply_markup=_build_keyboard(_resolve_links(it)),
                disable_web_page_preview=True
            )
            _mark_sent(chat_id, key)
            sent += 1
            await asyncio.sleep(0.35)
        except Exception as e:
            log.warning(f"send_message failed for {chat_id}: {e}")

def interleave_by_source(items: List[Dict]) -> List[Dict]:
    from collections import deque
    buckets = {}
    for it in items:
        src = (it.get("source") or "freelancer").lower()
        buckets.setdefault(src, []).append(it)
    dq = {k: deque(v) for k, v in buckets.items()}
    out = []
    while True:
        progressed = False
        for k in dq:
            if dq[k]:
                out.append(dq[k].popleft())
                progressed = True
        if not progressed:
            break
    return out

async def amain():
    token = os.getenv("TELEGRAM_BOT_TOKEN","") or os.getenv("BOT_TOKEN","")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    interval = int(os.getenv("WORKER_INTERVAL","120"))
    per_user_batch = int(os.getenv("BATCH_PER_TICK","5"))
    bot = Bot(token=token)

    users = _fetch_all_users()

    while True:
        cycle_start = datetime.now(timezone.utc)
        sent_total = 0
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=FRESH_HOURS)
            for tid in users:
                kws = _fetch_user_keywords(tid)
                items = await _worker.fetch_all(kws)

                # μέτρηση raw items ανά feed πριν τα φίλτρα
                for it in items:
                    src = (it.get("source") or "freelancer").lower()
                    stats_incr(src, 1)

                filtered = []
                for it in items:
                    mk = it.get("matched_keyword")
                    if not mk:
                        txt = (it.get("title","") + " " + it.get("description","")).lower()
                        for kw in kws:
                            if kw.lower() in txt:
                                mk = kw
                                break
                    if not mk:
                        continue
                    it["matched_keyword"] = mk

                    dt = _extract_dt(it)
                    if not dt or dt < cutoff:
                        continue

                    filtered.append(it)

                filtered.sort(key=lambda x: _extract_dt(x) or cutoff, reverse=True)
                mixed = interleave_by_source(filtered)

                if mixed:
                    await _send_items(bot, tid, mixed, per_user_batch)
                    sent_total += min(len(mixed), per_user_batch)

        except Exception as e:
            log.error(f"runner error: {e}")
            stats_error("worker", str(e))

        # γράφουμε stats για τον τρέχοντα κύκλο
        try:
            elapsed = (datetime.now(timezone.utc) - cycle_start).total_seconds()
            publish_stats(
                cycle_seconds=elapsed,
                sent_this_cycle=sent_total,
            )
        except Exception as e:
            log.warning("publish_stats failed: %s", e)

        await asyncio.sleep(interval)

if __name__ == "__main__":
    asyncio.run(amain())
