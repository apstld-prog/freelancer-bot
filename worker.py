# worker.py — robust dynamic platform loader, 60s interval, send-after-success marking

import os
import time
import logging
import importlib
from typing import Callable, Dict, List, Tuple

from sqlalchemy import text as sqltext
from telegram import Bot

from db import get_session
from job_logic import make_key  # match logic γίνεται μέσω keyword scan/local
from db_events import log_platform_event  # signature: log_platform_event(platform, count)

logging.basicConfig(level=logging.INFO, format="%(levelname)s:worker:%(message)s")
log = logging.getLogger("worker")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "60"))
bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None

# -------------------------------------------------
# DB helpers
# -------------------------------------------------
def ensure_sent_table():
    with get_session() as s:
        s.execute(sqltext("""
            CREATE TABLE IF NOT EXISTS sent_job (
                job_key TEXT PRIMARY KEY,
                sent_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC')
            )
        """))
        s.commit()

def prune_sent_table(days: int = 7):
    with get_session() as s:
        s.execute(sqltext("DELETE FROM sent_job WHERE sent_at < (NOW() AT TIME ZONE 'UTC') - INTERVAL :d || ' days'"),
                  {"d": days})
        s.commit()

def get_keywords() -> List[str]:
    with get_session() as s:
        rows = s.execute(sqltext("SELECT DISTINCT value FROM keyword")).fetchall()
        return [r[0] for r in rows]

def get_active_users() -> List[Tuple[int, int]]:
    with get_session() as s:
        # id, telegram_id από active και όχι blocked
        rows = s.execute(sqltext('SELECT id, telegram_id FROM "user" WHERE COALESCE(is_blocked, FALSE)=FALSE')).fetchall()
        return [(int(r[0]), int(r[1])) for r in rows if r[1]]

# -------------------------------------------------
# Platform loader (no hardcoded names)
# -------------------------------------------------
def load_fetcher(module_name: str) -> Callable[[object], List[Dict]]:
    """
    Επιστρέφει μία fetch συνάρτηση από το module:
    προτεραιότητα: fetch, fetch_jobs, fetch_<mod>_jobs, οτιδήποτε που ξεκινά με 'fetch'
    """
    mod = importlib.import_module(module_name)
    # candidate names
    base = module_name.replace("platform_", "")
    for fname in ("fetch", "fetch_jobs", f"fetch_{base}_jobs"):
        fn = getattr(mod, fname, None)
        if callable(fn):
            return fn
    # fallback: οποιαδήποτε callable που ξεκινάει με fetch
    for name in dir(mod):
        if name.startswith("fetch"):
            fn = getattr(mod, name)
            if callable(fn):
                return fn
    raise ImportError(f"No fetch function found in {module_name}")

def get_platforms() -> List[Tuple[str, Callable]]:
    names = [
        "platform_freelancer",
        "platform_peopleperhour",
        "platform_kariera",
        "platform_careerjet",
        "platform_skywalker",
    ]
    platforms = []
    for m in names:
        try:
            fn = load_fetcher(m)
            platforms.append((m.replace("platform_", ""), fn))
        except Exception as e:
            log.warning("Platform %s not available: %s", m, e)
    return platforms

# -------------------------------------------------
# Sending
# -------------------------------------------------
def build_text(item: Dict) -> str:
    title = (item.get("title") or "Untitled").strip()
    bmin = item.get("budget_min_usd") or item.get("budget_min") or item.get("budget_minimum")
    bmax = item.get("budget_max_usd") or item.get("budget_max") or item.get("budget_maximum")
    currency = "USD" if (item.get("budget_min_usd") or item.get("budget_max_usd")) else (item.get("currency") or "")
    if bmin and bmax:
        budget_str = f"{bmin}–{bmax} {currency}".strip()
    elif bmin:
        budget_str = f"{bmin} {currency}".strip()
    elif bmax:
        budget_str = f"{bmax} {currency}".strip()
    else:
        budget_str = "N/A"
    source = (item.get("source") or item.get("platform") or "unknown").title()
    desc = (item.get("description") or item.get("summary") or item.get("text") or "").strip()
    url = item.get("affiliate_url") or item.get("original_url") or item.get("url") or "#"
    text = (
        f"{title}\n"
        f"<b>Budget:</b> {budget_str}\n"
        f"<b>Source:</b> {source}\n\n"
        f"✏️ {desc[:1000]}\n\n"
        f"<a href='{url}'>🔗 Open Project</a>"
    )
    return text

def send_job_to_user(chat_id: int, item: Dict) -> bool:
    if not bot:
        log.warning("No BOT_TOKEN provided; skipping send.")
        return False
    try:
        text_msg = build_text(item)
        bot.send_message(chat_id=chat_id, text=text_msg, parse_mode="HTML", disable_web_page_preview=True,
                         reply_markup={
                             "inline_keyboard": [
                                 [{"text": "Proposal", "url": item.get("affiliate_url") or item.get("original_url") or item.get("url") or "#"},
                                  {"text": "Original", "url": item.get("original_url") or item.get("affiliate_url") or item.get("url") or "#"}],
                                 [{"text": "Save", "callback_data": "job:save"},
                                  {"text": "Delete", "callback_data": "job:delete"}]
                             ]
                         })
        return True
    except Exception as e:
        log.warning("send to %s failed: %s", chat_id, e)
        return False

# -------------------------------------------------
# Cycle
# -------------------------------------------------
def fetch_all(keywords: List[str]) -> List[Dict]:
    all_items: List[Dict] = []
    for name, fetcher in get_platforms():
        items: List[Dict] = []
        # Δοκιμάζουμε διαφορετικές μορφές για συμβατότητα
        for arg in (keywords, " ".join(keywords), [ " ".join(keywords) ]):
            try:
                res = fetcher(arg)
                if isinstance(res, list):
                    items = res
                    break
            except Exception as e:
                log.warning("[%s] fetch attempt with %s failed: %s", name, type(arg).__name__, e)
        if not items:
            log.warning("[%s] returned no items", name)
        for it in items:
            it.setdefault("source", name)
        all_items.extend(items)
        # event log (μην ρίχνουμε το worker αν αποτύχει)
        try:
            log_platform_event(name, len(items))
        except Exception as e:
            log.debug("log_platform_event failed: %s", e)
    return all_items

def deliver(items: List[Dict]):
    if not items:
        return
    users = get_active_users()
    log.info("[deliver] users loaded: %d", len(users))
    for item in items:
        key = make_key(item)
        # αν έχει ξανασταλεί, skip
        with get_session() as s:
            exists = s.execute(sqltext("SELECT 1 FROM sent_job WHERE job_key=:k"), {"k": key}).fetchone()
        if exists:
            continue
        # στείλε σε όλους — μαρκάρισε ως sent μόνο αν είχε έστω 1 επιτυχία
        success_any = False
        for _, tg in users:
            if send_job_to_user(tg, item):
                success_any = True
            time.sleep(0.2)
        if success_any:
            with get_session() as s:
                s.execute(sqltext("INSERT INTO sent_job(job_key) VALUES (:k) ON CONFLICT DO NOTHING"), {"k": key})
                s.commit()

def main():
    log.info("[Worker] ✅ Running (interval=%ss)", WORKER_INTERVAL)
    ensure_sent_table()
    while True:
        try:
            prune_sent_table(7)
            keywords = get_keywords()
            items = fetch_all(keywords)
            log.info("[Worker] cycle completed — keywords=%d, items=%d", len(keywords), len(items))
            deliver(items)
        except Exception as e:
            log.error("[Worker] error: %s", e)
        time.sleep(WORKER_INTERVAL)

if __name__ == "__main__":
    main()
