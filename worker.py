# worker.py
import time
from typing import List, Dict, Optional

import platform_freelancer as fr
import platform_skywalker as sky
import platform_placeholders as ph
import platform_peopleperhour as pph

from config import SKYWALKER_RSS

PLATFORMS = {
    "freelancer": True,
    "peopleperhour": True,
    "skywalker": True,
    "malt": True,
    "workana": True,
    "wripple": True,
    "toptal": True,
    "twago": True,
    "freelancermap": True,
    "yunoJuno": True,
    "worksome": True,
    "codeable": True,
    "guru": True,
    "99designs": True,
    "jobfind": True,
    "kariera": True,
    "careerjet": True,
}

# -------------------------------------------------------------
# 🔵 FETCH ALL (Freelancer + Skywalker + PPH με premium proxy)
# -------------------------------------------------------------
def fetch_all(keywords_query: Optional[str] = None) -> List[Dict]:
    out=[]
    kwlist = []
    if isinstance(keywords_query, str):
        kwlist = [keywords_query]
    elif isinstance(keywords_query, list):
        kwlist = keywords_query

    # --- FREELANCER ---
    if PLATFORMS.get("freelancer"):
        try:
            out += fr.fetch(keywords_query or None)
        except Exception:
            pass

    # --- PEOPLEPERHOUR (premium proxy version) ---
    if PLATFORMS.get("peopleperhour"):
        try:
            for it in pph.get_items(kwlist):
                it["affiliate"] = False
                it["source"] = "peopleperhour"
                out.append(it)
        except Exception:
            pass

    # --- SKYWALKER ---
    if PLATFORMS.get("skywalker"):
        try:
            for it in sky.fetch(SKYWALKER_RSS):
                it["affiliate"] = False
                it["source"] = "skywalker"
                out.append(it)
        except Exception:
            pass

    # --- OTHER PLACEHOLDERS (unchanged) ---
    try:
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
    except Exception:
        pass

    return out

# -------------------------------------------------------------
# 🔵 RUN PIPELINE (unchanged)
# -------------------------------------------------------------
def run_pipeline(keywords: List[str]) -> List[Dict]:
    return fetch_all(keywords)
