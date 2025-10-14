# worker.py
# Collects jobs from enabled platforms, filters by keywords, deduplicates,
# annotates matched keyword, and prepares budget in original currency + USD.

from typing import List, Dict, Optional
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

# Ensure feed events table exists (safe no-op if exists)
ensure_schema()


# ---------- keyword matching ----------
def _normalize_kw_list(keywords: Optional[List[str]]) -> List[str]:
    if not keywords:
        return []
    return [(k or "").strip().lower() for k in keywords if (k or "").strip()]


def match_keywords(item: Dict, keywords: List[str]) -> Optional[str]:
    """
    Returns the matched keyword (lowercase) if any, otherwise None.
    If keywords list is empty → treat as match (return None to indicate 'no specific kw').
    """
    if not keywords:
        return None
    title = (item.get("title") or "").lower()
    desc = (item.get("description") or "").lower()
    hay = f"{title}\n{desc}"
    for kw in keywords:
        if kw and kw in hay:
            return kw
    return None


# ---------- fetch from platforms ----------
def fetch_all(keywords_query: Optional[str] = None) -> List[Dict]:
    """
    Pull jobs from enabled sources. For freelancer.com we can pass a comma-sep query
    to help upstream filtering (fast pre-filter); we still re-check locally.
    """
    out: List[Dict] = []

    # Freelancer.com (affiliate-capable)
    if PLATFORMS.get("freelancer"):
        try:
            out += fr.fetch(keywords_query or None)
        except Exception:
            pass

    # Skywalker RSS
    if PLATFORMS.get("skywalker"):
        try:
            for i in sky.fetch(SKYWALKER_RSS):
                i["affiliate"] = False
                out.append(i)
        except Exception:
            pass

    # Placeholders (controlled by flags; most return [])
    try:
        if PLATFORMS.get("peopleperhour"): out += ph.fetch_peopleperhour()
        if PLATFORMS.get("malt"): out += ph.fetch_malt()
        if PLATFORMS.get("workana"): out += ph.fetch_workana()
        if PLATFORMS.get("wripple"): out += ph.fetch_wripple()
        if PLATFORMS.get("toptal"): out += ph.fetch_toptal()
        if PLATFORMS.get("twago"): out += ph.fetch_twago()
        if PLATFORMS.get("freelancermap"): out += ph.fetch_freelancermap()
        if PLATFORMS.get("younojuno") or PLATFORMS.get("yunoJuno") or PLATFORMS.get("yuno_juno"):
            out += ph.fetch_yunojuno()
        if PLATFORMS.get("worksome"): out += ph.fetch_worksome()
        if PLATFORMS.get("codeable"): out += ph.fetch_codeable()
        if PLATFORMS.get("guru"): out += ph.fetch_guru()
        if PLATFORMS.get("99designs"): out += ph.fetch_99designs()
        # Greece
        if PLATFORMS.get("jobfind"): out += ph.fetch_jobfind()
        if PLATFORMS.get("kariera"): out += ph.fetch_kariera()
        if PLATFORMS.get("careerjet"): out += ph.fetch_careerjet()
    except Exception:
        # swallow placeholders errors
        pass

    return out


# ---------- dedup ----------
def _job_key(item: Dict) -> str:
    try:
        return make_key(item)
    except Exception:
        # fallback
        sid = str(item.get("id") or item.get("original_url") or item.get("url") or item.get("title") or "")[:512]
        return f"{item.get('source','unknown')}::{sid}"


def deduplicate(items: List[Dict]) -> List[Dict]:
    """
    Keep best per dedup key. Prefer affiliate versions when duplicates found.
    """
    keep: Dict[str, Dict] = {}
    for it in items:
        k = _job_key(it)
        if k in keep:
            try:
                keep[k] = prefer_affiliate(keep[k], it)
            except Exception:
                # simple keep-first if helper fails
                pass
        else:
            keep[k] = it
    return list(keep.values())


# ---------- display preparation ----------
def prepare_display(item: Dict, rates: Dict) -> Dict:
    """
    Returns a shallow copy with computed USD fields. Does NOT change strings presentation;
    presentation happens in runner (_compose_message).
    """
    out = dict(item)
    ccy = out.get("currency")
    for fld in ("budget_min", "budget_max"):
        val = out.get(fld)
        out[fld + "_usd"] = to_usd(val, ccy, rates)
    return out


def wrap_freelancer(url: str) -> str:
    """
    Ensure consistent deep-linking for both Proposal and Original via affiliate prefix.
    """
    if not url:
        return url
    return f"{AFFILIATE_PREFIX_FREELANCER}&dl={url}"


# ---------- pipeline ----------
def run_pipeline(keywords: Optional[List[str]]) -> List[Dict]:
    """
    Main orchestrator used by worker_runner:
    - load FX rates from env
    - upstream fetch (with optional query for freelancer)
    - local keyword filter + annotate matched keyword
    - dedup
    - prepare USD values for display
    - record per-platform fetch events (stats)
    """
    rates = load_fx_rates(FX_USD_RATES)

    # Prepare upstream query hint (comma-separated) for platforms that support it
    kw_norm = _normalize_kw_list(keywords)
    query = ",".join(kw_norm) if kw_norm else None

    # Fetch raw items
    items = fetch_all(keywords_query=query)

    # Local keyword matching and annotation
    filtered: List[Dict] = []
    for it in items:
        mk = match_keywords(it, kw_norm)
        if kw_norm and mk is None:
            # If user has keywords, keep only matches
            continue
        if mk:
            it["matched_keyword"] = mk
        filtered.append(it)

    # Deduplicate
    filtered = deduplicate(filtered)

    # Prepare for display + record platform usage
    final: List[Dict] = []
    for it in filtered:
        final.append(prepare_display(it, rates))
        try:
            log_platform_event(it.get("source", "unknown"))
        except Exception:
            pass

    return final
