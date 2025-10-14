# worker.py — fetch, per-user filter, annotate match, dedup, currency prepare (robust INR/EUR/£/₹, etc.)

from typing import List, Dict, Optional, Tuple
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

ensure_schema()

# ---------- keyword helpers ----------
def _normalize_kw_list(keywords: Optional[List[str]]) -> List[str]:
    if not keywords: return []
    return [(k or "").strip().lower() for k in keywords if (k or "").strip()]

def match_keywords(item: Dict, keywords: List[str]) -> Optional[str]:
    if not keywords: return None
    hay = f"{(item.get('title') or '').lower()}\n{(item.get('description') or '').lower()}"
    for kw in keywords:
        if kw and kw in hay:
            return kw
    return None

# ---------- fetch ----------
def fetch_all(keywords_query: Optional[str] = None) -> List[Dict]:
    out: List[Dict] = []
    if PLATFORMS.get("freelancer"):
        try:
            out += fr.fetch(keywords_query or None)
        except Exception:
            pass
    if PLATFORMS.get("skywalker"):
        try:
            for i in sky.fetch(SKYWALKER_RSS):
                i["affiliate"] = False
                out.append(i)
        except Exception:
            pass
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
        if PLATFORMS.get("jobfind"): out += ph.fetch_jobfind()
        if PLATFORMS.get("kariera"): out += ph.fetch_kariera()
        if PLATFORMS.get("careerjet"): out += ph.fetch_careerjet()
    except Exception:
        pass
    return out

# ---------- dedup ----------
def _job_key(item: Dict) -> str:
    try:
        return make_key(item)
    except Exception:
        sid = str(item.get("id") or item.get("original_url") or item.get("url") or item.get("title") or "")[:512]
        return f"{item.get('source','unknown')}::{sid}"

def deduplicate(items: List[Dict]) -> List[Dict]:
    keep: Dict[str, Dict] = {}
    for it in items:
        k = _job_key(it)
        if k in keep:
            try:
                keep[k] = prefer_affiliate(keep[k], it)
            except Exception:
                pass
        else:
            keep[k] = it
    return list(keep.values())

# ---------- currency detection ----------
_SYMBOL_TO_CODE = {
    "€":"EUR","£":"GBP","₹":"INR","₽":"RUB","₺":"TRY","¥":"JPY","₩":"KRW","₪":"ILS",
    "R$":"BRL","A$":"AUD","C$":"CAD","$":"USD"  # generic $ as last resort
}

def _detect_currency(item: Dict) -> Tuple[str, str]:
    """
    Returns (code, display). Display prefers symbol if provided, otherwise code.
    Extremely defensive: checks multiple fields + scans text for common symbols (₹ € £).
    """
    # 1) obvious fields from parsers
    code = (item.get("currency_code") or item.get("currency") or item.get("budget_currency") or item.get("original_currency") or "")
    code = str(code).upper().strip() if code else ""
    sym  = (item.get("currency_symbol") or item.get("currency_display") or "").strip()

    # 2) infer from symbol mapping
    if not code and sym:
        code = _SYMBOL_TO_CODE.get(sym, "")

    # 3) scan title/desc for symbols if still unknown
    if not code:
        txt = f"{item.get('title') or ''}\n{item.get('description') or ''}"
        for s,c in [("₹","INR"),("€","EUR"),("£","GBP")]:
            if s in txt:
                code = c; sym = s; break

    if not code:
        code = "USD"
    display = sym or code
    return code, display

def prepare_display(item: Dict, rates: Dict) -> Dict:
    out = dict(item)
    code, display = _detect_currency(out)
    out["currency_code_detected"] = code
    out["currency_display"] = out.get("currency_display") or display
    for fld in ("budget_min", "budget_max"):
        val = out.get(fld)
        out[fld + "_usd"] = to_usd(val, code, rates)
    return out

def wrap_freelancer(url: str) -> str:
    if not url: return url
    return f"{AFFILIATE_PREFIX_FREELANCER}&dl={url}"

# ---------- pipeline ----------
def run_pipeline(keywords: Optional[List[str]]) -> List[Dict]:
    rates = load_fx_rates(FX_USD_RATES)
    kw_norm = _normalize_kw_list(keywords)
    query = ",".join(kw_norm) if kw_norm else None

    items = fetch_all(keywords_query=query)

    filtered: List[Dict] = []
    for it in items:
        mk = match_keywords(it, kw_norm)
        if kw_norm and mk is None:
            continue
        if mk:
            it["matched_keyword"] = mk
        filtered.append(it)

    filtered = deduplicate(filtered)

    final: List[Dict] = []
    for it in filtered:
        final.append(prepare_display(it, rates))
        try:
            log_platform_event(it.get("source", "unknown"))
        except Exception:
            pass
    return final
