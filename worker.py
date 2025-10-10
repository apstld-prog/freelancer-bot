# worker.py
import logging
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

log = logging.getLogger("worker")

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
    log.info("Fetching sources... keywords_query=%s", keywords_query)
    out: List[Dict] = []

    # Freelancer.com — affiliate-capable
    if PLATFORMS.get("freelancer"):
        _b=len(out)
        query = keywords_query or None
        out += fr.fetch(query=query)
        log.info("Freelancer fetched: %d", len(out)-_b)

    # Skywalker RSS
    if PLATFORMS.get("skywalker"):
        _before = len(out)
        for i in sky.fetch(SKYWALKER_RSS):
            i["affiliate"] = False
            out.append(i)
        log.info("Careerjet fetched: %d", len(out)-_b)
        log.info("Skywalker fetched: %d", len(out)-_before)

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
    if PLATFORMS.get("kariera"):
        _b=len(out) out += ph.fetch_kariera()
    if PLATFORMS.get("careerjet"):
        _b=len(out) out += ph.fetch_careerjet()

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
    log.info("Total fetched before filter: %d", len(items))
    _before_filter = len(items)
    items = [i for i in items if match_keywords(i, keywords)]
    log.info("After keyword filter: %d (filtered out %d)", len(items), _before_filter - len(items))
    _before_dedup = len(items)
    items = deduplicate(items)
    log.info("After dedup: %d (removed %d duplicates)", len(items), _before_dedup - len(items))
    final = []
    for it in items:
        final.append(prepare_display(it, rates))
        log_platform_event(it.get("source", "unknown"))
    return final

def wrap_freelancer(url: str) -> str:
    # Ensure consistent deep-linking for both Proposal and Original
    return f"{AFFILIATE_PREFIX_FREELANCER}&dl={url}"
