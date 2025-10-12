import os
import time
import logging
from typing import Dict, List, Tuple
from importlib import import_module

from sqlalchemy import text as sqltext
from telegram import Bot

from db import get_session
from job_logic import make_key, match_keywords
from db_events import log_platform_event  # already exists in your repo

logging.basicConfig(level=logging.INFO, format="%(levelname)s:worker:%(message)s")
log = logging.getLogger("worker")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "60"))
bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None

# ---------- DB helpers ----------

def ensure_sent_table() -> None:
    with get_session() as s:
        s.execute(sqltext("""
            CREATE TABLE IF NOT EXISTS sent_job (
                job_key TEXT PRIMARY KEY,
                sent_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC')
            )
        """))
        s.commit()

def prune_sent_table(days: int = 7) -> None:
    # keep dedup store small
    with get_session() as s:
        s.execute(
            sqltext("DELETE FROM sent_job WHERE sent_at < (NOW() AT TIME ZONE 'UTC') - INTERVAL :d || ' days'"),
            {"d": days},
        )
        s.commit()

def get_keywords() -> List[str]:
    with get_session() as s:
        rows = s.execute(sqltext("SELECT DISTINCT value FROM keyword")).fetchall()
        return [r[0] for r in rows]

def get_active_users() -> List[Tuple[int, int]]:
    with get_session() as s:
        rows = s.execute(sqltext('SELECT id, telegram_id FROM "user" WHERE COALESCE(is_blocked, FALSE)=FALSE')).fetchall()
        return [(int(r[0]), int(r[1])) for r in rows if r[1]]

# ---------- Platforms (no UI changes) ----------

PLATFORM_MODULES = [
    "platform_freelancer",
    "platform_peopleperhour",
    "platform_skywalker",
    # add others later without touching UI
]

def _resolve_fetch_func(module_name: str):
    mod = import_module(module_name)
    base = module_name.replace("platform_", "")
    for name in ("fetch", "fetch_jobs", f"fetch_{base}_jobs"):
        fn = getattr(mod, name, None)
        if callable(fn):
            return fn
    # fallback: any callable starting with fetch
    for name in dir(mod):
        if name.startswith("fetch"):
            fn = getattr(mod, name)
            if callable(fn):
                return fn
    raise ImportError(f"No fetch function in {module_name}")

def fetch_all(keywords: List[str]) -> List[Dict]:
    items: List[Dict] = []
    for m in PLATFORM_MODULES:
        try:
            fetcher = _resolve_fetch_func(m)
        except Exception as e:
            log.warning("Platform %s not available: %s", m, e)
            continue

        got = []
        # try list and space-joined forms – some modules expect one or the other
        for arg in (keywords, " ".join(keywords), [" ".join(keywords)]):
            try:
                res = fetcher(arg)
                if isinstance(res, list):
                    got = res
                    break
            except Exception as e:
                log.warning("[%s] fetch attempt failed (%s): %s", m, type(arg).__name__, e)

        for it in got:
            it.setdefault("platform", m.replace("platform_", ""))
        items.extend(got)

        try:
            log_platform_event(m.replace("platform_", ""), "fetch")
        except Exception as e:
            log.debug("log_platform_event failed: %s", e)

    return items

# ---------- Sending (keeps your card layout text) ----------

def render_text(item: Dict, match_word: str = "") -> str:
    # This text matches your existing card style (title + Budget/Source/Match + description)
    title = (item.get("title") or "Untitled").strip()
    desc = (item.get("description") or "").strip()

    # Budget formatting (do not change labels)
    bmin = item.get("budget_min_usd") or item.get("budget_min") or item.get("budget")
    bmax = item.get("budget_max_usd") or item.get("budget_max")
    cur = "USD" if (item.get("budget_min_usd") or item.get("budget_max_usd")) else (item.get("currency") or "USD")

    if bmin and bmax:
        budget_str = f"{bmin:.1f}–{bmax:.1f} {cur}"
    elif bmin:
        budget_str = f"{float(bmin):.1f} {cur}"
    elif bmax:
        budget_str = f"{float(bmax):.1f} {cur}"
    else:
        budget_str = "N/A"

    source = (item.get("source") or item.get("platform") or "Freelancer").title()
    match_str = match_word or (item.get("match") or "")

    parts = [
        f"{title}",
        f"  🧾  Budget: {budget_str}",
        f"  🧭  Source: {source}",
        f"  🔎  Match: {match_str}" if match_str else "  🔎  Match: —",
        f"  📝  {desc}",
    ]
    return "\n".join(parts)

def send_job_message(chat_id: int, item: Dict, text_msg: str) -> bool:
    if not bot:
        log.warning("No BOT_TOKEN; cannot send.")
        return False

    # Buttons: preserve Proposal / Original / Save / Delete
    original = item.get("original_url") or item.get("url") or "#"
    proposal = item.get("affiliate_url") or original

    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "📄 Proposal", "url": proposal},
                {"text": "🔗 Original", "url": original},
            ],
            [
                {"text": "⭐ Save", "callback_data": f"job:save:{make_key(item)}"},
                {"text": "🗑️ Delete", "callback_data": "job:delete"},
            ],
        ]
    }

    try:
        bot.send_message(
            chat_id=chat_id,
            text=text_msg,
            parse_mode="HTML",              # text is plain; HTML safe
            disable_web_page_preview=True,
            reply_markup=reply_markup,
        )
        return True
    except Exception as e:
        log.warning("Send failed to %s: %s", chat_id, e)
        return False

def deliver(items: List[Dict], keywords: List[str]) -> None:
    if not items:
        return
    users = get_active_users()
    log.info("[deliver] users loaded: %d", len(users))

    for it in items:
        key = make_key(it)
        with get_session() as s:
            exists = s.execute(sqltext("SELECT 1 FROM sent_job WHERE job_key=:k"), {"k": key}).fetchone()
        if exists:
            continue

        # choose first matching keyword (for "Match:" line); fallback empty
        match_word = ""
        try:
            text_blob = f"{it.get('title','')} {it.get('description','')}".lower()
            for kw in keywords:
                if kw.lower() in text_blob:
                    match_word = kw
                    break
        except Exception:
            pass

        if not match_keywords(it, keywords):
            continue

        text_msg = render_text(it, match_word)
        success_any = False
        for _, tg in users:
            if send_job_message(tg, it, text_msg):
                success_any = True
            time.sleep(0.15)

        if success_any:
            with get_session() as s:
                s.execute(sqltext("INSERT INTO sent_job(job_key) VALUES (:k) ON CONFLICT DO NOTHING"), {"k": key})
                s.commit()

# ---------- Main loop ----------

def main():
    log.info("[Worker] ✅ Running (interval=%ss)", WORKER_INTERVAL)
    ensure_sent_table()
    while True:
        try:
            prune_sent_table(7)
            keywords = get_keywords()
            items = fetch_all(keywords)
            log.info("[Worker] cycle completed — keywords=%d, items=%d", len(keywords), len(items))
            deliver(items, keywords)
        except Exception as e:
            log.error("[Worker] error: %s", e)
        time.sleep(WORKER_INTERVAL)

if __name__ == "__main__":
    main()
