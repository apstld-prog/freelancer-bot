import httpx
from typing import List, Dict

PPH_PROXY_BASE = "https://pph-proxy-chris.fly.dev/pph"

def get_items(keywords: List[str]) -> List[Dict]:
    """
    Καλεί τον PPH proxy (FastAPI) και επιστρέφει τα jobs όπως τα δίνει ο proxy.
    """
    kws = [k.strip() for k in (keywords or []) if k and k.strip()]
    if not kws:
        return []

    q = ",".join(kws)
    try:
        r = httpx.get(PPH_PROXY_BASE, params={"q": q}, timeout=30.0)
        r.raise_for_status()
        data = r.json()
        jobs = data.get("jobs") or []
        for it in jobs:
            it.setdefault("source", "peopleperhour")
        return jobs
    except Exception:
        return []
