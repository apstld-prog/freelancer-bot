import os
import time
import logging
from typing import List, Dict, Optional

from config import (
    PLATFORMS,
    SKYWALKER_RSS,
    CAREERJET_RSS,
    KARIERA_RSS,
    FX_USD_RATES,
)

import platform_skywalker as sky
import platform_freelancer as fr
import platform_peopleperhour as pph
import platform_careerjet as cj
import platform_kariera as kr

try:
    from utils import match_keywords
except Exception:
    def match_keywords(item: Dict, keywords: List[str]) -> bool:
        title = (item.get("title") or "").lower()
        desc = (item.get("description") or "").lower()
        return any(k.lower() in title or k.lower() in desc for k in keywords)

try:
    from dedup import deduplicate
except Exception:
    def deduplicate(items: List[Dict]) -> List[Dict]:
        seen = set()
        out = []
        for i in items:
            key = i.get("url") or i.get("title")
            if key and key not in seen:
                seen.add(key)
                out.append(i)
        return out

try:
    from utils_fx import load_fx_rates, to_usd
except Exception:
    def load_fx_rates(_): return {}
    def to_usd(amount, currency, rates): return amount

log = logging.getLogger("worker")
logging.basicConfig(level=logging.INFO)

def _interval_seconds() -> int:
    val = os.getenv("WORKER_INTERVAL", "120")
    try:
        return max(30, int(val))
    except Exception:
        return 120

def fetch_all(keywords_query: Optional[str] = None) -> List[Dict]:
    out: List[Dict] = []
    log.info("Fetching sources... keywords_query=%s", keywords_query)

    if PLATFORMS.get("skywalker"):
        _b = len(out)
        for i in sky.fetch(SKYWALKER_RSS):
            i["affiliate"] = False
            out.append(i)
        log.info("Skywalker fetched: %d", len(out) - _b)

    if PLATFORMS.get("peopleperhour"):
        _b = len(out)
        out += pph.fetch(query=keywords_query or None)
        log.info("PeoplePerHour fetched: %d", len(out) - _b)

    if PLATFORMS.get("careerjet"):
        _b = len(out)
        for i in cj.fetch(CAREERJET_RSS):
            i["affiliate"] = False
            out.append(i)
        log.info("Careerjet fetched: %d", len(out) - _b)

    if PLATFORMS.get("kariera"):
        _b = len(out)
        for i in kr.fetch(KARIERA_RSS):
            i["affiliate"] = False
            out.append(i)
        log.info("Kariera fetched: %d", len(out) - _b)

    if PLATFORMS.get("freelancer"):
        _b = len(out)
        out += fr.fetch(query=keywords_query or None)
        log.info("Freelancer fetched: %d", len(out) - _b)

    return out

def main():
    interval = _interval_seconds()
    rates = load_fx_rates(FX_USD_RATES) if 'FX_USD_RATES' in globals() else {}
    keywords: List[str] = []  # keyword filtering may be applied downstream in your pipeline

    while True:
        try:
            items = fetch_all()
            log.info("Total fetched before filter: %d", len(items))
            _bf = len(items)
            items = [i for i in items if match_keywords(i, keywords)] if keywords else items
            log.info("After keyword filter: %d (filtered out %d)", len(items), _bf - len(items))
            _bd = len(items)
            items = deduplicate(items)
            log.info("After dedup: %d (removed %d duplicates)", len(items), _bd - len(items))
        except Exception as e:
            log.exception("Worker iteration error: %s", e)
        time.sleep(interval)

if __name__ == "__main__":
    main()
