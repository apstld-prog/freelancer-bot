
# --------------------------------------------------------------
# 🧹 Prune sent_job entries older than N days
# --------------------------------------------------------------
def prune_sent_table(days: int = 7) -> None:
    from db import get_session
    from sqlalchemy import text as sqltext
    with get_session() as s:
        s.execute(sqltext("DELETE FROM sent_job WHERE sent_at < (NOW() AT TIME ZONE 'UTC') - INTERVAL :d || ' days'").bindparams(d=days))
        s.commit()

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


# --------------------------------------------------------------
# ⏱ Keep only items not older than N days (default 7)
# --------------------------------------------------------------
def is_recent(item: Dict, days: int = 7) -> bool:
    from datetime import datetime, timezone, timedelta
    from email.utils import parsedate_to_datetime

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    # Candidate fields commonly used by our sources
    for key in ("created_at", "published_at", "pub_date", "date"):
        dt = item.get(key)
        if not dt:
            continue
        # If it's already a datetime
        if hasattr(dt, 'tzinfo') or isinstance(dt, datetime):
            try:
                return dt >= cutoff
            except Exception:
                pass
        # Try ISO 8601
        if isinstance(dt, str):
            try:
                # Normalize Z
                s = dt.replace("Z", "+00:00")
                dti = datetime.fromisoformat(s)
                if dti.tzinfo is None:
                    dti = dti.replace(tzinfo=timezone.utc)
                return dti >= cutoff
            except Exception:
                # Try RFC 2822 (RSS)
                try:
                    dti = parsedate_to_datetime(dt)
                    if dti.tzinfo is None:
                        dti = dti.replace(tzinfo=timezone.utc)
                    return dti >= cutoff
                except Exception:
                    pass
        # Try unix timestamp
        try:
            ts = float(dt)
            dti = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dti >= cutoff
        except Exception:
            continue
    # If no usable date found, keep it (don't discard)
    return True

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

            log.info("[Worker] cycle completed — keywords=%d, items=%d",
                     len(keywords), len(_items))
        except Exception as e:
            log.exception("[Worker] cycle error: %s", e)

        time.sleep(interval)
