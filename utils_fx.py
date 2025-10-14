# utils_fx.py — FX helpers (original → USD)
# Reads rates from env FX_USD_RATES (JSON). Falls back to sane defaults.
# Rates are USD per 1 unit of original currency (e.g., 1 INR = 0.012 USD).

from __future__ import annotations
import os, json
from typing import Dict, Optional

# Conservative defaults (μπορείς να τα αλλάξεις μέσω env)
DEFAULT_FX_USD_RATES: Dict[str, float] = {
    "USD": 1.0,
    "EUR": 1.09,
    "GBP": 1.27,
    "INR": 0.012,   # ~0.012 USD per 1 INR
    "AUD": 0.66,
    "CAD": 0.73,
    "JPY": 0.0067,
    "KRW": 0.00073,
    "TRY": 0.033,
    "BRL": 0.18,
    "ILS": 0.26,
    "RUB": 0.011,
}

def load_fx_rates(env_key: str = "FX_USD_RATES") -> Dict[str, float]:
    """Merge ENV JSON with defaults. Keys upper-cased."""
    raw = os.getenv(env_key, "").strip()
    merged = dict(DEFAULT_FX_USD_RATES)
    if raw:
        try:
            data = json.loads(raw)
            for k, v in (data or {}).items():
                if not k: 
                    continue
                try:
                    vv = float(v)
                except Exception:
                    continue
                if vv > 0:
                    merged[str(k).upper()] = vv
        except Exception:
            # ignore malformed env
            pass
    return merged

def to_usd(value: Optional[float], ccy: Optional[str], rates: Dict[str, float]) -> Optional[float]:
    """Convert `value` from `ccy` to USD using provided rates."""
    if value is None:
        return None
    try:
        v = float(value)
    except Exception:
        return None
    code = (ccy or "USD").upper()
    rate = rates.get(code)
    if rate is None:
        # last resort: if unknown code, assume 1.0 only for USD; otherwise fail
        if code == "USD":
            rate = 1.0
        else:
            return None
    usd = v * rate
    # Formatting hint: return with 0 decimals for large values, 1 for small
    if usd >= 100:
        return round(usd)  # no decimals
    return round(usd, 1)
