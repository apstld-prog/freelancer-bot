# currency_usd.py
# Drop-in helper for showing "~ $minâ€“$max USD" lines.
# Î”ÎµÎ½ Î­Ï‡ÎµÎ¹ ÎµÎ¾Ï‰Ï„ÎµÏÎ¹ÎºÎ¬ dependencies. Rates ÎµÎ¯Î½Î±Î¹ conservative,
# Î¼Îµ fallback ÏƒÎµ 1:1 Î±Î½ Î´ÎµÎ½ Î²ÏÎµÎ¸ÎµÎ¯ Î½ÏŒÎ¼Î¹ÏƒÎ¼Î± (Î¿Ï€ÏŒÏ„Îµ Î±Ï€Î»Î¬ Î´ÎµÎ½ Î¸Î± Ï„Ï…Ï€ÏŽÏƒÎµÎ¹ USD).
# Î¤ÎµÎ»ÎµÏ…Ï„Î±Î¯Î± ÎµÎ½Î·Î¼Î­ÏÏ‰ÏƒÎ· Ï€Î¹Î½Î¬ÎºÎ±: 2025-10-01 (Ï€ÏÎ¿ÏƒÎµÎ³Î³Î¹ÏƒÏ„Î¹ÎºÎ¬ mid-market).

from typing import Optional, Tuple

# Î ÏÎ¿ÏƒÎµÎ³Î³Î¹ÏƒÏ„Î¹ÎºÎ­Ï‚ Î¹ÏƒÎ¿Ï„Î¹Î¼Î¯ÎµÏ‚ -> USD
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
    # Ï€ÏÏŒÏƒÎ¸ÎµÏƒÎµ Î±Î½ Ï‡ÏÎµÎ¹Î±ÏƒÏ„ÎµÎ¯Ï‚ ÎºÎ¹ Î¬Î»Î»Î±
}

def to_usd_range(min_amount: Optional[float],
                 max_amount: Optional[float],
                 currency: Optional[str]) -> Optional[Tuple[float, float]]:
    """ÎœÎµÏ„Î±Ï„ÏÎ­Ï€ÎµÎ¹ Ï€ÏÎ¿Î±Î¹ÏÎµÏ„Î¹ÎºÏŒ range ÏƒÎµ USD. Î•Ï€Î¹ÏƒÏ„ÏÎ­Ï†ÎµÎ¹ (min_usd, max_usd) Î® None."""
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
    # Î‘Î½ ÎºÎ±Î¹ Ï„Î± Î´ÏÎ¿ None, Î´ÎµÎ½ Ï„Ï…Ï€ÏŽÎ½Î¿Ï…Î¼Îµ Ï„Î¯Ï€Î¿Ï„Î±
    if min_usd is None and max_usd is None:
        return None
    return (min_usd or 0.0, max_usd or 0.0)

def usd_line(min_amount: Optional[float],
             max_amount: Optional[float],
             currency: Optional[str]) -> Optional[str]:
    """Î•Ï€Î¹ÏƒÏ„ÏÎ­Ï†ÎµÎ¹ Ï„Î·Î½ Î­Ï„Î¿Î¹Î¼Î· Î³ÏÎ±Î¼Î¼Î® Ï€.Ï‡. '~ $100.00â€“$300.00 USD' Î® None."""
    rng = to_usd_range(min_amount, max_amount, currency)
    if not rng:
        return None
    lo, hi = rng
    if lo and hi:
        return f"~ ${lo:,.2f}â€“${hi:,.2f} USD"
    if lo and not hi:
        return f"~ from ${lo:,.2f} USD"
    if hi and not lo:
        return f"~ up to ${hi:,.2f} USD"
    return None




