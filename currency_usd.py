# currency_usd.py
# Helper for converting platform budget ranges into approximate USD values.
# No external dependencies. Rates are mid-market and conservative.

from typing import Optional, Tuple

# Base currency conversion table -> USD
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
    # Additional currencies can be added here.
}


def to_usd_range(min_amount: Optional[float],
                 max_amount: Optional[float],
                 currency: Optional[str]) -> Optional[Tuple[float, float]]:
    """
    Converts (min_amount, max_amount, currency_code) to approximate USD values.
    Returns: (min_usd, max_usd) or None if conversion is not possible.
    """
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
    """
    Returns a printable USD range line, e.g. "~ $100.00–$300.00 USD".
    """
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
