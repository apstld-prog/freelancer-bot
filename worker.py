
import os, time, logging
from typing import List, Dict, Optional

from config import PLATFORMS, SKYWALKER_RSS, CAREERJET_RSS, KARIERA_RSS, FX_USD_RATES
import platform_skywalker as sky
import platform_freelancer as fr
import platform_peopleperhour as pph
import platform_careerjet as cj
import platform_kariera as kr

try:
    from utils import match_keywords
except Exception:
    def match_keywords(i: Dict, kws: List[str]) -> bool:
        t = (i.get("title") or "").lower(); d = (i.get("description") or "").lower()
        return any(k.lower() in t or k.lower() in d for k in kws)

try:
    from dedup import deduplicate
except Exception:
    def deduplicate(items: List[Dict]) -> List[Dict]:
        seen, out = set(), []
        for x in items:
            key = x.get("url") or x.get("title")
            if key and key not in seen:
                seen.add(key); out.append(x)
        return out

try:
    from utils_fx import load_fx_rates, to_usd
except Exception:
    def load_fx_rates(_): return {}
    def to_usd(a, c, r): return a

log = logging.getLogger("worker")
logging.basicConfig(level=logging.INFO)

def _interval() -> int:
    try:
        return max(30, int(os.getenv("WORKER_INTERVAL", "120")))
    except Exception:
        return 120

def fetch_all(keywords_query: Optional[str] = None) -> List[Dict]:
    out: List[Dict] = []
    log.info("Fetching sources... keywords_query=%s", keywords_query)

    if PLATFORMS.get("skywalker"):
        _b = len(out)
        for i in sky.fetch(SKYWALKER_RSS):
            i["affiliate"] = False; out.append(i)
        log.info("Skywalker fetched: %d", len(out)-_b)

    if PLATFORMS.get("peopleperhour"):
        _b = len(out)
        out += pph.fetch(query=keywords_query or None)
        log.info("PeoplePerHour fetched: %d", len(out)-_b)

    if PLATFORMS.get("careerjet"):
        _b = len(out)
        for i in cj.fetch(CAREERJET_RSS):
            i["affiliate"] = False; out.append(i)
        log.info("Careerjet fetched: %d", len(out)-_b)

    if PLATFORMS.get("kariera"):
        _b = len(out)
        for i in kr.fetch(KARIERA_RSS):
            i["affiliate"] = False; out.append(i)
        log.info("Kariera fetched: %d", len(out)-_b)

    if PLATFORMS.get("freelancer"):
        _b = len(out)
        out += fr.fetch(query=keywords_query or None)
        log.info("Freelancer fetched: %d", len(out)-_b)

    return out

def main():
    interval = _interval()
    rates = load_fx_rates(FX_USD_RATES) if 'FX_USD_RATES' in globals() else {}
    filter_mode = os.getenv("KEYWORD_FILTER_MODE", "on").lower()
    kws: List[str] = []

    while True:
        try:
            items = fetch_all()
            log.info("Total fetched before filter: %d", len(items))
            _bf = len(items)
            if filter_mode != "off" and kws:
                items = [i for i in items if match_keywords(i, kws)]
            log.info("After keyword filter: %d (filtered out %d)", len(items), _bf - len(items))
            _bd = len(items)
            items = deduplicate(items)
            log.info("After dedup: %d (removed %d duplicates)", len(items), _bd - len(items))
        except Exception as e:
            log.exception("Worker iteration error: %s", e)
        time.sleep(interval)

if __name__ == "__main__":
    main()
