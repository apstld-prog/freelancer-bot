import asyncio
import logging
import os
import time
from typing import Dict, List
import httpx
from sqlalchemy import text as sqltext
from db import get_session
from db_events import ensure_feed_events_schema as ensure_schema
from job_logic import match_keywords, make_key

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker")


# -------------------------------------------------
# Import μόνο σταθερές πλατφόρμες που δουλεύουν
# -------------------------------------------------
def _import_fetch(module_name: str):
    mod = __import__(module_name, fromlist=["*"])
    for fn in ("fetch", "fetch_jobs", f"fetch_{module_name.split('_', 1)[1]}_jobs"):
        if hasattr(mod, fn):
            return getattr(mod, fn)
    for name in dir(mod):
        if name.startswith("fetch") and callable(getattr(mod, name)):
            return getattr(mod, name)
    raise ImportError(f"No fetcher found in {module_name}")


PLATFORMS = []
for name in [
    "platform_freelancer",
    "platform_peopleperhour",
    # "platform_skywalker",  # temporarily disabled due to fetch error
]:
    try:
        fetcher = _import_fetch(name)
        PLATFORMS.append((name.replace("platform_", ""), fetcher))
    except Exception as e:
        log.warning("Platform %s not available: %s", name, e)


async def maybe_await(result):
    if asyncio.iscoroutine(result):
        return await result
    return result


def ensure_sent_table():
    with get_session() as s:
        s.execute(
            sqltext(
                """
            CREATE TABLE IF NOT EXISTS sent_job (
                job_key TEXT PRIMARY KEY,
                sent_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC')
            );
        """
            )
        )
        s.commit()


def prune_sent_table(days: int = 7):
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with get_session() as s:
        s.execute(sqltext("DELETE FROM sent_job WHERE sent_at < :cutoff"), {"cutoff": cutoff})
        s.commit()


def is_recent(item: Dict, days: int = 7) -> bool:
    from datetime import datetime, timezone, timedelta
    from email.utils import parsedate_to_datetime

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    for key in ("created_at", "published_at", "pub_date", "date"):
        dt = item.get(key)
        if not dt:
            continue
        if hasattr(dt, "tzinfo"):
            try:
                return dt >= cutoff
            except Exception:
                pass
        if isinstance(dt, str):
            try:
                s = dt.replace("Z", "+00:00")
                dti = datetime.fromisoformat(s)
            except Exception:
                try:
                    dti = parsedate_to_datetime(dt)
                except Exception:
                    dti = None
            if dti is not None:
                if dti.tzinfo is None:
                    dti = dti.replace(tzinfo=timezone.utc)
                return dti >= cutoff
        try:
            ts = float(dt)
            dti = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dti >= cutoff
        except Exception:
            continue
    return True


def find_match_keyword(item: Dict, keywords: List[str]) -> str | None:
    text_parts = []
    for k in ("title", "description", "summary", "text"):
        v = item.get(k)
        if isinstance(v, str):
            text_parts.append(v.lower())
    if not text_parts:
        return None
    full = " ".join(text_parts)
    for kw in keywords:
        if not kw:
            continue
        k = kw.strip().lower()
        if k and k in full:
            return kw
    return None


# -------------------------------------------------
# SEND: επιστρέφει True/False και ΔΕΝ καταχωρεί τίποτα στη βάση
# -------------------------------------------------
def send_job_to_user(chat_id: int, item: Dict) -> bool:
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
    if not BOT_TOKEN:
        log.warning("No BOT_TOKEN set; skipping send.")
        return False

    TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    title = (item.get("title") or "Untitled").strip()
    bmin = item.get("budget_min_usd") or item.get("budget_min")
    bmax = item.get("budget_max_usd") or item.get("budget_max")
    cur = "USD" if (item.get("budget_min_usd") or item.get("budget_max_usd")) else (item.get("currency") or "")
    if bmin and bmax:
        budget_str = f"{bmin}–{bmax} {cur}".strip()
    elif bmin:
        budget_str = f"{bmin} {cur}".strip()
    elif bmax:
        budget_str = f"{bmax} {cur}".strip()
    else:
        budget_str = "N/A"

    source = (item.get("source") or "unknown").title()
    match_kw = item.get("match") or "-"
    desc = (item.get("description") or item.get("summary") or item.get("text") or "").strip()
    orig = item.get("original_url") or item.get("url") or ""
    aff = item.get("affiliate_url") or orig

    text_msg = (
        f"{title}\n"
        f"<b>Budget:</b> {budget_str}\n"
        f"<b>Source:</b> {source}\n"
        f"<b>Match:</b> {match_kw}\n\n"
        f"✏️ {desc}"
    )

    kb = {
        "inline_keyboard": [
            [{"text": "Proposal", "url": aff or orig}, {"text": "Original", "url": orig or aff}],
            [{"text": "Save", "callback_data": "job:save"}, {"text": "Delete", "callback_data": "job:delete"}],
        ]
    }

    try:
        r = httpx.post(
            TG_API,
            json={
                "chat_id": chat_id,
                "text": text_msg,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "reply_markup": kb,
            },
            timeout=20,
        )
        ok = (r.status_code == 200) and (r.json().get("ok") is True)
        if not ok:
            log.warning("[send] to %s failed: %s %s", chat_id, r.status_code, r.text[:200])
        return ok
    except Exception as e:
        log.warning("[send] to %s exception: %s", chat_id, e)
        return False


# -------------------------------------------------
# DELIVER: αποστολή πρώτα • καταχώριση sent_job ΜΟΝΟ αν υπήρξε επιτυχία
# -------------------------------------------------
def deliver_to_users(items: List[Dict]):
    if not items:
        return

    ensure_sent_table()

    # users
    with get_session() as s:
        rows = s.execute(sqltext('SELECT id, telegram_id FROM "user" WHERE is_blocked=FALSE')).fetchall()
        users = [(int(r[0]), int(r[1])) for r in rows]
        log.info("[deliver] users loaded: %d", len(users))

    for item in items:
        key = make_key(item)

        # αν υπάρχει ήδη, προχώρα στο επόμενο
        with get_session() as s:
            exists = s.execute(sqltext("SELECT 1 FROM sent_job WHERE job_key=:k"), {"k": key}).fetchone()
        if exists:
            continue

        success_any = False
        for _, tid in users:
            if send_job_to_user(tid, item):
                success_any = True
            time.sleep(0.3)

        if success_any:
            with get_session() as s:
                s.execute(sqltext("INSERT INTO sent_job(job_key) VALUES (:k) ON CONFLICT DO NOTHING"), {"k": key})
                s.commit()


# -------------------------------------------------
# Main pipeline with multi-format retry
# -------------------------------------------------
async def run_pipeline(keywords: List[str]):
    all_items = []
    for src, fetcher in PLATFORMS:
        items = []
        for form in (keywords, " ".join(keywords), [" ".join(keywords)]):
            try:
                items = await maybe_await(fetcher(form))
                if items:
                    break
            except Exception as e:
                log.warning("[%s] fetch try failed (%s): %s", src, type(form).__name__, e)
        if not items:
            log.error("[%s] fetch error after retries.", src)
            continue
        for it in items:
            it.setdefault("source", src)
        all_items.extend(items)

    filtered = []
    for it in all_items:
        mk = find_match_keyword(it, keywords)
        if mk and is_recent(it, 7):
            it["match"] = mk
            filtered.append(it)

    log.info("[Worker] cycle completed — keywords=%d, items=%d", len(keywords), len(filtered))
    deliver_to_users(filtered)


def get_keywords() -> List[str]:
    with get_session() as s:
        rows = s.execute(sqltext("SELECT DISTINCT value FROM keyword")).fetchall()
        return [r[0] for r in rows]


if __name__ == "__main__":
    interval = int(os.getenv("WORKER_INTERVAL", "120"))
    log.info("[Worker] ✅ Running (interval=%ss)", interval)
    ensure_schema()
    ensure_sent_table()

    while True:
        try:
            prune_sent_table(7)
            kw = get_keywords()
            asyncio.run(run_pipeline(kw))
        except Exception as e:
            log.error("[Worker] error: %s", e)
        time.sleep(interval)
