# currency_usd.py — fixed version with backward compatibility

from typing import Optional, Tuple

_RATES_TO_USD = {
    "USD": 1.0,
    "EUR": 1.08,
    "GBP": 1.27,
    "INR": 0.012,
    "AUD": 0.66,
    "CAD": 0.73,
    "SGD": 0.73,
    "PLN": 0.25,
    "RON": 0.21,
    "TRY": 0.033,
    "SEK": 0.09,
    "NOK": 0.09,
    "DKK": 0.145,
    "CHF": 1.10,
    "CZK": 0.041,
    "HUF": 0.0027,
    "JPY": 0.0066,
    "ZAR": 0.055,
}

def to_usd_range(min_amount: Optional[float],
                 max_amount: Optional[float],
                 currency: Optional[str]) -> Optional[Tuple[float, float]]:
    """Convert range to USD tuple (min_usd, max_usd) or None."""
    if not currency:
        return None
    cur = currency.upper().strip()
    rate = _RATES_TO_USD.get(cur)
    if not rate:
        return None
    def conv(x: Optional[float]) -> Optional[float]:
        return round(float(x) * rate, 2) if x is not None else None
    min_usd = conv(min_amount)
    max_usd = conv(max_amount)
    if min_usd is None and max_usd is None:
        return None
    return (min_usd or 0.0, max_usd or 0.0)

def usd_line(min_amount: Optional[float],
             max_amount: Optional[float],
             currency: Optional[str]) -> Optional[str]:
    """Return formatted '~ $100–$300 USD' line or None."""
    rng = to_usd_range(min_amount, max_amount, currency)
    if not rng:
        return None
    lo, hi = rng
    if lo and hi:
        return f"~ ${lo:,.2f}–${hi:,.2f} USD"
    if lo and not hi:
        return f"~ from ${lo:,.2f} USD"
    if hi and not lo:
        return f"~ up to ${hi:,.2f} USD"
    return None

# ✅ Backward compatibility (workers expect this name)
def convert_to_usd(min_amount: Optional[float],
                   max_amount: Optional[float],
                   currency: Optional[str]) -> Optional[Tuple[float, float]]:
    """Alias for to_usd_range — kept for legacy worker imports."""
    return to_usd_range(min_amount, max_amount, currency)
