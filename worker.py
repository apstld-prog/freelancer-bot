# worker.py
from typing import List, Dict
from config import (
    PLATFORMS, SKYWALKER_RSS, FX_USD_RATES,
    AFFILIATE_PREFIX_FREELANCER
)
from utils_fx import load_fx_rates, to_usd
from dedup import make_key, prefer_affiliate
import platform_skywalker as sky
import platform_placeholders as ph
import platform_freelancer as fr
from db_events import ensure_schema, log_platform_event

# Ensure the events table exists at import time (safe no-op if already there)
ensure_schema()

def match_keywords(item: Dict, keywords: List[str]) -> bool:
    if not keywords:
        return True
    title = item.get("title", "") or ""
    desc = item.get("description", "") or ""
    hay = f"{title}\n{desc}".lower()
    return any((kw or "").strip().lower() in hay for kw in keywords if (kw or "").strip())

def fetch_all(keywords_query: str = None) -> List[Dict]:
    out: List[Dict] = []

    # Freelancer.com — affiliate-capable
    if PLATFORMS.get("freelancer"):
        query = keywords_query or None
        out += fr.fetch(query=query)

    # Skywalker RSS
    if PLATFORMS.get("skywalker"):
        for i in sky.fetch(SKYWALKER_RSS):
            i["affiliate"] = False
            out.append(i)

    # Placeholders (currently return [])
    if PLATFORMS.get("peopleperhour"): out += ph.fetch_peopleperhour()
    if PLATFORMS.get("malt"): out += ph.fetch_malt()
    if PLATFORMS.get("workana"): out += ph.fetch_workana()
    if PLATFORMS.get("wripple"): out += ph.fetch_wripple()
    if PLATFORMS.get("toptal"): out += ph.fetch_toptal()
    if PLATFORMS.get("twago"): out += ph.fetch_twago()
    if PLATFORMS.get("freelancermap"): out += ph.fetch_freelancermap()
    if PLATFORMS.get("yunoJuno"): out += ph.fetch_yunojuno()
    if PLATFORMS.get("worksome"): out += ph.fetch_worksome()
    if PLATFORMS.get("codeable"): out += ph.fetch_codeable()
    if PLATFORMS.get("guru"): out += ph.fetch_guru()
    if PLATFORMS.get("99designs"): out += ph.fetch_99designs()
    if PLATFORMS.get("jobfind"): out += ph.fetch_jobfind()
    if PLATFORMS.get("kariera"): out += ph.fetch_kariera()
    if PLATFORMS.get("careerjet"): out += ph.fetch_careerjet()

    return out

def deduplicate(items: List[Dict]) -> List[Dict]:
    seen = {}
    for it in items:
        k = make_key(it)
        if k in seen:
            seen[k] = prefer_affiliate(seen[k], it)
        else:
            seen[k] = it
    return list(seen.values())

def prepare_display(item: Dict, rates: dict) -> Dict:
    for fld in ["budget_min", "budget_max"]:
        if item.get(fld) is not None and item.get("currency"):
            item[fld + "_usd"] = to_usd(item.get(fld), item.get("currency"), rates)
    return item

def run_pipeline(keywords: List[str]) -> List[Dict]:
    rates = load_fx_rates(FX_USD_RATES)
    query = ",".join([k.strip() for k in keywords if k and k.strip()]) if keywords else None
    items = fetch_all(keywords_query=query)
    items = [i for i in items if match_keywords(i, keywords)]
    items = deduplicate(items)
    final = []
    for it in items:
        final.append(prepare_display(it, rates))
        log_platform_event(it.get("source", "unknown"))
    return final

def wrap_freelancer(url: str) -> str:
    # Ensure consistent deep-linking for both Proposal and Original
    return f"{AFFILIATE_PREFIX_FREELANCER}&dl={url}"



# --------------------------------------------------------------
# 🚀 Deliver new matching jobs to users
# --------------------------------------------------------------
def deliver_to_users(items: List[Dict]) -> None:
    """Send job alerts to each user whose keywords match (minimal, no UI changes)."""
    import os
    import httpx
    from db import get_session
    from sqlalchemy import text as sqltext

    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
    if not BOT_TOKEN:
        return
    TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    with get_session() as s:
        rows = s.execute(sqltext('SELECT id, telegram_id FROM "user" WHERE is_active=TRUE AND is_blocked=FALSE')).fetchall()
        users = [(int(r[0]), int(r[1])) for r in rows]

    for uid, chat_id in users:
        with get_session() as s:
            kw_rows = s.execute(sqltext("SELECT value FROM keyword WHERE user_id=:u"), {"u": uid}).fetchall()
            user_keywords = [r[0] for r in kw_rows if r and r[0]]

        for it in items:
            if not match_keywords(it, user_keywords):
                continue

            title = it.get("title", "Untitled")
            bmin = it.get("budget_min_usd") or it.get("budget_min")
            bmax = it.get("budget_max_usd") or it.get("budget_max")
            cur  = "USD" if (it.get("budget_min_usd") or it.get("budget_max_usd")) else (it.get("currency") or "")
            if bmin and bmax:
                budget_str = f"{bmin}–{bmax} {cur}".strip()
            elif bmin:
                budget_str = f"{bmin} {cur}".strip()
            elif bmax:
                budget_str = f"{bmax} {cur}".strip()
            else:
                budget_str = "N/A"

            orig = it.get("original_url") or it.get("url") or ""
            aff  = it.get("affiliate_url") or (wrap_freelancer(orig) if (orig and it.get("source") == "freelancer") else orig)

            text_msg = (
                f"💼 <b>{title}</b>\n"
                f"💰 <b>Budget:</b> {budget_str}\n"
                f"📦 <b>Source:</b> {it.get('source','unknown').title()}\n"
            )

            kb = {
                "inline_keyboard": [
                    [{"text": "📄 Proposal", "url": aff or orig},
                     {"text": "🔗 Original", "url": orig or aff}],
                    [{"text": "⭐ Save", "callback_data": "job:save"},
                     {"text": "🗑️ Delete", "callback_data": "job:delete"}]
                ]
            }

            try:
                httpx.post(
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
            except Exception as e:
                print(f"[deliver_to_users] send fail to {chat_id}: {e}")

# --------------------------------------------------------------
# 🧠 Worker main loop
# --------------------------------------------------------------
if __name__ == "__main__":
    import os, time, logging
    from sqlalchemy import text
    from db import get_session

    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("worker")

    interval = int(os.getenv("WORKER_INTERVAL", "120"))
    log.info("[Worker] ✅ Running (interval=%ss)", interval)

    while True:
        try:
            # Fetch all distinct keywords from DB
            with get_session() as s:
                rows = s.execute(text("SELECT DISTINCT value FROM keyword")).fetchall()
            keywords = [r[0] for r in rows if r and r[0]]

            # Run the full pipeline (fetch, match, dedup, record events)
            _items = run_pipeline(keywords)

            # deliver alerts to users
            deliver_to_users(_items)

            log.info("[Worker] cycle completed — keywords=%d, items=%d",
                     len(keywords), len(_items))
        except Exception as e:
            log.exception("[Worker] cycle error: %s", e)

        time.sleep(interval)
