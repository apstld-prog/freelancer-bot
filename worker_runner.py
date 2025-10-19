#!/usr/bin/env python3
import os, sys, time, importlib, traceback, datetime as dt
from typing import Any, Dict, List, Optional, Tuple

# -------------------------------
# Helpers
# -------------------------------
def _now_utc() -> dt.datetime:
    return dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)

def _hours_ago(hours: int) -> dt.datetime:
    return _now_utc() - dt.timedelta(hours=hours)

def _log(msg: str) -> None:
    print(msg, flush=True)

def _fmt_exc() -> str:
    return "".join(traceback.format_exc())

# -------------------------------
# Dynamic safe caller
# -------------------------------
def _try_call(func, keywords, fresh_since, limit, logger):
    """
    Δοκιμάζει διάφορα signatures ώστε να παίξει με παλιά modules
    χωρίς να χρειαστεί να τα αλλάξουμε.
    """
    # Πλήρες signature (προτιμώμενο)
    try:
        return func(keywords=keywords, fresh_since=fresh_since, limit=limit, logger=logger)
    except TypeError:
        pass
    # keywords, fresh_since, limit
    try:
        return func(keywords, fresh_since, limit)
    except TypeError:
        pass
    # keywords, limit
    try:
        return func(keywords, limit)
    except TypeError:
        pass
    # keywords μόνο
    try:
        return func(keywords)
    except TypeError:
        pass
    # χωρίς args
    try:
        return func()
    except TypeError:
        pass
    # Τελευταία προσπάθεια με kwargs χωρίς logger
    try:
        return func(keywords=keywords, fresh_since=fresh_since, limit=limit)
    except TypeError:
        pass
    return []

def _resolve_fetch_func(mod) -> Tuple[str, Any]:
    """
    Επιστρέφει (όνομα, συνάρτηση) για την πρώτη διαθέσιμη συνάρτηση
    που μοιάζει να φέρνει αγγελίες.
    """
    preferred = [
        "get_items",
        "fetch_items",
        "fetch",
        "search",
        "list_items",
        "scrape",
        "run",
        "main",
    ]
    for name in preferred:
        if hasattr(mod, name) and callable(getattr(mod, name)):
            return name, getattr(mod, name)

    # fallback: ψάξε οποιοδήποτε callable με "item" ή "job" στο όνομα
    for name in dir(mod):
        if name.startswith("_"):
            continue
        obj = getattr(mod, name)
        if callable(obj) and any(tok in name.lower() for tok in ["item", "job", "feed", "fetch", "search", "scrape"]):
            return name, obj

    raise AttributeError("Δεν βρέθηκε κατάλληλη συνάρτηση fetch στο module.")

def _safe_get(mod, keywords, fresh_since, limit, log_prefix=""):
    """
    Φέρνει items από ένα module χωρίς να σκάει σε παλιά signatures.
    """
    try:
        func_name, func = _resolve_fetch_func(mod)
        _log(f"DEBUG: using {mod.__name__}.{func_name}()")
        items = _try_call(func, keywords, fresh_since, limit, logger=None) or []
        return items
    except Exception as e:
        _log(f"ERROR:{log_prefix}{mod.__name__} fetch failed\n{_fmt_exc()}")
        return []

# -------------------------------
# Intervals / config
# -------------------------------
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "60"))  # γενικό fallback
FRESH_WINDOW_HOURS = int(os.getenv("FRESH_WINDOW_HOURS", "48"))

# Ανά πλατφόρμα intervals (override του γενικού)
FREELANCER_INTERVAL_SECONDS = int(os.getenv("FREELANCER_INTERVAL_SECONDS", str(WORKER_INTERVAL)))
PPH_INTERVAL_SECONDS         = int(os.getenv("PPH_INTERVAL_SECONDS", "600"))  # 10' default

ENABLE_FREELANCER = os.getenv("ENABLE_FREELANCER", "1") == "1"
ENABLE_PPH        = os.getenv("ENABLE_PPH", "1") == "1"

# -------------------------------
# Import platforms (χωρίς να σκάμε αν λείπει κάποια)
# -------------------------------
def _import_optional(name: str):
    try:
        return importlib.import_module(name)
    except Exception:
        _log(f"WARNING: cannot import {name} — {traceback.format_exc(limit=1).strip()}")
        return None

mod_freelancer = _import_optional("platform_freelancer") if ENABLE_FREELANCER else None
mod_pph        = _import_optional("platform_peopleperhour") if ENABLE_PPH else None

# -------------------------------
# Keywords source
# -------------------------------
def _load_keywords() -> List[str]:
    raw = os.getenv("KEYWORDS", "")  # comma-separated
    kws = [k.strip() for k in raw.split(",") if k.strip()]
    return kws[:50]  # ασφάλεια

# -------------------------------
# Main worker loop
# -------------------------------
def _tick_once():
    keywords = _load_keywords()
    fresh_since = _hours_ago(FRESH_WINDOW_HOURS)
    limit = int(os.getenv("FETCH_LIMIT", "30"))

    fetched_total = {}

    # FREELANCER
    if mod_freelancer:
        items = _safe_get(mod_freelancer, keywords, fresh_since, limit, log_prefix="freelancer: ")
        _log(f"INFO:worker:freelancer fetched={len(items)}")
        fetched_total["freelancer"] = len(items)

    # PPH
    if mod_pph:
        items = _safe_get(mod_pph, keywords, fresh_since, limit, log_prefix="pph: ")
        _log(f"INFO:worker:peopleperhour fetched={len(items)}")
        fetched_total["peopleperhour"] = len(items)

    _log(f"INFO:worker:[tick] sources={fetched_total}")

def main():
    _log("[Worker] Starting background process (compat invoker enabled)...")
    next_run = {
        "freelancer": 0.0,
        "pph":        0.0,
    }

    while True:
        now = time.time()
        ran_any = False

        # FREELANCER slot
        if mod_freelancer and now >= next_run["freelancer"]:
            _tick_once()  # μέσα κάνει και pph αν είναι ώρα – θέλουμε ξεκάθαρο log; εναλλακτικά τρέχουμε ανά πλατφόρμα
            next_run["freelancer"] = now + FREELANCER_INTERVAL_SECONDS
            ran_any = True

        # PPH slot (αν θέλουμε να εγγυηθούμε ξεχωριστό ρυθμό)
        if mod_pph and now >= next_run["pph"]:
            # τρέχουμε μόνο PPH αυτή τη φορά για να κρατήσουμε το interval καθαρό
            keywords = _load_keywords()
            fresh_since = _hours_ago(FRESH_WINDOW_HOURS)
            limit = int(os.getenv("FETCH_LIMIT", "30"))
            items = _safe_get(mod_pph, keywords, fresh_since, limit, log_prefix="pph: ")
            _log(f"INFO:worker:peopleperhour fetched={len(items)}")
            next_run["pph"] = now + PPH_INTERVAL_SECONDS
            ran_any = True

        if not ran_any:
            # περιμένουμε ως το επόμενο slot
            sleep_for = min(
                max(0.5, next_run["freelancer"] - now) if mod_freelancer else 9999,
                max(0.5, next_run["pph"] - now)        if mod_pph        else 9999,
            )
            time.sleep(sleep_for)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        _log("[Worker] stopped.")
    except Exception:
        _log(f"[Worker] crashed:\n{_fmt_exc()}")
        sys.exit(1)
