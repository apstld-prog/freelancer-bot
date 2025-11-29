# worker.py
# Ενιαίος worker που φέρνει αγγελίες από όλες τις πλατφόρμες
# Χωρίς αλλαγή στο UI, μόνο στη λογική fetch_all(keywords)

from typing import List, Dict
import logging

from platform_freelancer import get_items as _freelancer_items
from platform_skywalker import get_items as _skywalker_items
from platform_peopleperhour_http import get_items as pph_items
from platform_upwork_http import get_items as upwork_items

from worker_stats_sidecar import incr, error

# Αν θέλεις αργότερα να προσθέσεις κι άλλες πλατφόρμες:
# from platform_peopleperhour_playwright import get_items as _pph_items
# from platform_kariera import get_items as _kariera_items
# from platform_careerjet import get_items as _careerjet_items

log = logging.getLogger("worker")

async def fetch_all(keywords: List[str]) -> List[Dict]:
    """
    Ενιαία είσοδος για τον worker_runner.
    Δέχεται τις λέξεις-κλειδιά του χρήστη και επιστρέφει ΟΛΕΣ τις αγγελίες
    από όλες τις πλατφόρμες, σε ενιαία λίστα.
    Ο worker_runner αναλαμβάνει το matching, το φιλτράρισμα χρόνου και το UI.
    """
    keywords = [k.strip() for k in (keywords or []) if k and k.strip()]
    if not keywords:
        return []
    all_items: List[Dict] = []

    # 1) Freelancer
    try:
        fl_items = _freelancer_items(keywords)
        incr("freelancer", len(fl_items))
        log.info(f"[worker] Freelancer returned {len(fl_items)} items")
        all_items.extend(fl_items)
    except Exception as e:
        error("freelancer", str(e))
        log.warning(f"[worker] Freelancer fetch failed: {e}")
        
    # 2) Skywalker
    try:
        sky_items = _skywalker_items(keywords)
        incr("skywalker", len(sky_items))
        log.info(f"[worker] Skywalker returned {len(sky_items)} items")
        all_items.extend(sky_items)
    except Exception as e:
        error("skywalker", str(e))
        log.warning(f"[worker] Skywalker fetch failed: {e}")
    
    # 3) PeoplePerHour (μέσω proxy, sync HTTP)
    try:
        pph_jobs = pph_items(keywords)
        incr("peopleperhour", len(pph_jobs))
        log.info(f"[worker] PeoplePerHour returned {len(pph_jobs)} items")
        all_items.extend(pph_jobs)
    except Exception as e:
        error("peopleperhour", str(e))
        log.warning(f"[worker] PeoplePerHour fetch failed: {e}")
    
    # 4) Upwork (HTML + cookies)
    try:
        up_items = upwork_items(keywords)
        incr("upwork", len(up_items))
        log.info(f"[worker] Upwork returned {len(up_items)} items")
        all_items.extend(up_items)
    except Exception as e:
        error("upwork", str(e))
        log.warning(f"[worker] Upwork fetch failed: {e}")

    # 2) Άλλες πλατφόρμες (PPH, Kariera, Skywalker, Careerjet κ.λπ.)
    #    Όταν είναι έτοιμα τα get_items για αυτές, απλώς τα ξεσχολιάζεις:

    # try:
    #     kj_items = _kariera_items(keywords)
    #     log.info(f"[worker] Kariera returned {len(kj_items)} items for keywords={keywords}")
    #     all_items.extend(kj_items)
    # except Exception as e:
    #     log.warning(f"[worker] Kariera fetch failed: {e}")

    # try:
    #     cj_items = _careerjet_items(keywords)
    #     log.info(f"[worker] Careerjet returned {len(cj_items)} items for keywords={keywords}")
    #     all_items.extend(cj_items)
    # except Exception as e:
    #     log.warning(f"[worker] Careerjet fetch failed: {e}")

    return all_items
