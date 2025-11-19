# ---------------- worker.py (PPH fix — final) ----------------
from typing import List, Dict, Optional
from config import PLATFORMS, SKYWALKER_RSS, FX_USD_RATES, AFFILIATE_PREFIX_FREELANCER
from utils_fx import load_fx_rates, to_usd
from dedup import make_key, prefer_affiliate
import platform_skywalker as sky
import platform_placeholders as ph
import platform_freelancer as fr
import platform_peopleperhour as pph
from db_events import ensure_feed_events_schema as ensure_schema, record_event as log_platform_event
import time, datetime

ensure_schema()

def _normalize_kw_list(keywords: Optional[List[str]]) -> List[str]:
    if not keywords: return []
    return [(k or '').strip().lower() for k in keywords if (k or '').strip()]

def match_keywords(item: Dict, keywords: List[str]) -> Optional[str]:
    if not keywords: return None
    hay = f"{(item.get('title') or '').lower()}\n{(item.get('description') or '').lower()}"
    for kw in keywords:
        if kw and kw in hay:
            return kw
    return None

def fetch_all(keywords_query: Optional[str] = None) -> List[Dict]:
    out: List[Dict] = []

    # FREELANCER
    if PLATFORMS.get("freelancer"):
        try: out += fr.fetch(keywords_query or None)
        except: pass

    # PEOPLEPERHOUR (scraper gives matched_keyword)
    if PLATFORMS.get("peopleperhour"):
        try:
            kws = _normalize_kw_list(keywords_query.split(",") if keywords_query else [])
            for i in pph.get_items(kws):
                i["source"] = "peopleperhour"
                i["affiliate"] = False
                out.append(i)
        except: pass

    # SKYWALKER
    if PLATFORMS.get("skywalker"):
        try:
            for i in sky.fetch(SKYWALKER_RSS):
                i["source"] = "skywalker"
                i["affiliate"] = False
                out.append(i)
        except: pass

    # PLACEHOLDERS
    try:
        if PLATFORMS.get("malt"): out += ph.fetch_malt()
        if PLATFORMS.get("workana"): out += ph.fetch_workana()
        if PLATFORMS.get("wripple"): out += ph.fetch_wripple()
        if PLATFORMS.get("toptal"): out += ph.fetch_toptal()
        if PLATFORMS.get("twago"): out += ph.fetch_twago()
        if PLATFORMS.get("freelancermap"): out += ph.fetch_freelancermap()
        if PLATFORMS.get("younojuno") or PLATFORMS.get("yunoJuno") or PLATFORMS.get("yuno_juno"): out += ph.fetch_yunojuno()
        if PLATFORMS.get("worksome"): out += ph.fetch_worksome()
        if PLATFORMS.get("codeable"): out += ph.fetch_codeable()
        if PLATFORMS.get("guru"): out += ph.fetch_guru()
        if PLATFORMS.get("99designs"): out += ph.fetch_99designs()
        if PLATFORMS.get("jobfind"): out += ph.fetch_jobfind()
        if PLATFORMS.get("kariera"): out += ph.fetch_kariera()
        if PLATFORMS.get("careerjet"): out += ph.fetch_careerjet()
    except: pass

    return out

def _job_key(item: Dict) -> str:
    try: return make_key(item)
    except:
        sid = str(item.get("external_id") or item.get("url") or item.get("title") or "")[:512]
        return f"{item.get('source','unknown')}::{sid}"

def deduplicate(items: List[Dict]) -> List[Dict]:
    keep = {}
    for it in items:
        k = _job_key(it)
        if k in keep:
            try: keep[k] = prefer_affiliate(keep[k], it)
            except: pass
        else:
            keep[k] = it
    return list(keep.values())

def _humanize_ago(ts):
    try:
        now = int(time.time())
        diff = max(0, now - int(ts))
        if diff < 60: return "just now"
        m = diff // 60
        if m < 60: return f"{m} min ago"
        h = m // 60
        if h < 24: return f"{h} h ago"
        d = h // 24
        if d < 7: return f"{d} d ago"
        return datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
    except: return None

def prepare_display(item: Dict, rates: Dict) -> Dict:
    out = dict(item)
    cur = item.get("original_currency") or item.get("currency") or "USD"

    for fld in ("budget_min", "budget_max"):
        out[fld+"_usd"] = to_usd(item.get(fld), cur, rates)

    ts = item.get("time_submitted")
    if ts: out["posted_ago"] = _humanize_ago(ts)
    return out

def run_pipeline(keywords: Optional[List[str]]) -> List[Dict]:
    rates = load_fx_rates(FX_USD_RATES)
    kw_norm = _normalize_kw_list(keywords)
    query = ",".join(kw_norm) if kw_norm else None

    items = fetch_all(query)
    filtered = []

    for it in items:
        mk = match_keywords(it, kw_norm)

        # -------------------------
        # FIX: PEOPLEPERHOUR PASSES ALWAYS
        # -------------------------
        if it.get("source") == "peopleperhour":
            if mk:
                it["matched_keyword"] = mk
            filtered.append(it)
            continue

        # Other platforms = normal filtering
        if kw_norm and mk is None:
            continue
        if mk:
            it["matched_keyword"] = mk
        filtered.append(it)

    filtered = deduplicate(filtered)

    final = []
    for it in filtered:
        final.append(prepare_display(it, rates))
        try: log_platform_event(it.get("source","unknown"))
        except: pass

    return final
