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
from db_events import ensure_feed_events_schema as ensure_schema, record_event as log_platform_event

# Ensure the events table exists at import time (safe no-op if already there)
ensure_schema()

from sqlalchemy import text as _sql_text
from db import get_session as _get_session
import os as _os, logging as _logging

_wlog = _logging.getLogger("worker")

def _cleanup_old_sent_jobs(_days:int=7):
    """
    Delete old sent_job rows older than `_days` days.
    1) Try param-safe make_interval(days => :d)
    2) Fallback to constant INTERVAL '{days} days' (after int cast)
    Supports env override: WORKER_CLEANUP_DAYS=0 to disable silently.
    """
    try:
        _days = int(_days)
    except Exception:
        _days = 7

    # Allow disabling via env (0/false)
    _toggle = str(_os.getenv("WORKER_CLEANUP_DAYS", _days)).strip().lower()
    if _toggle in ("0", "false"):
        _wlog.info("[cleanup] skipped via WORKER_CLEANUP_DAYS=0")
        return

    # First attempt: make_interval
    try:
        with _get_session() as s:
            _wlog.info("[cleanup] using make_interval days=%s", _days)
            s.execute(
                _sql_text(
                    "DELETE FROM sent_job "
                    "WHERE sent_at < (NOW() AT TIME ZONE 'UTC') - make_interval(days => :d)"
                ),
                {"d": int(_days)}
            )
            s.commit()
            return
    except Exception as _e:
        _wlog.error("[cleanup] make_interval failed: %s", _e)

    # Fallback (constant INTERVAL)
    try:
        with _get_session() as s:
            _wlog.info("[cleanup] fallback constant interval days=%s", _days)
            s.execute(
                _sql_text(
                    "DELETE FROM sent_job "
                    f"WHERE sent_at < (NOW() AT TIME ZONE 'UTC') - INTERVAL '{int(_days)} days'"
                )
            )
            s.commit()
    except Exception as _e2:
        _wlog.error("[cleanup] fallback failed: %s", _e2)

# run once on import
try:
    _cleanup_old_sent_jobs(7)
except Exception as _e:
    _wlog.error("[cleanup] unexpected error: %s", _e)


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
