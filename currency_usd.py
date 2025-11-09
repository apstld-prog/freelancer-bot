# currency_usd.py
# Drop-in helper for showing "~ $minÃ¢â‚¬â€œ$max USD" lines.
# ÃŽâ€ÃŽÂµÃŽÂ½ ÃŽÂ­Ãâ€¡ÃŽÂµÃŽÂ¹ ÃŽÂµÃŽÂ¾Ãâ€°Ãâ€žÃŽÂµÃÂÃŽÂ¹ÃŽÂºÃŽÂ¬ dependencies. Rates ÃŽÂµÃŽÂ¯ÃŽÂ½ÃŽÂ±ÃŽÂ¹ conservative,
# ÃŽÂ¼ÃŽÂµ fallback ÃÆ’ÃŽÂµ 1:1 ÃŽÂ±ÃŽÂ½ ÃŽÂ´ÃŽÂµÃŽÂ½ ÃŽÂ²ÃÂÃŽÂµÃŽÂ¸ÃŽÂµÃŽÂ¯ ÃŽÂ½ÃÅ’ÃŽÂ¼ÃŽÂ¹ÃÆ’ÃŽÂ¼ÃŽÂ± (ÃŽÂ¿Ãâ‚¬ÃÅ’Ãâ€žÃŽÂµ ÃŽÂ±Ãâ‚¬ÃŽÂ»ÃŽÂ¬ ÃŽÂ´ÃŽÂµÃŽÂ½ ÃŽÂ¸ÃŽÂ± Ãâ€žÃâ€¦Ãâ‚¬ÃÅ½ÃÆ’ÃŽÂµÃŽÂ¹ USD).
# ÃŽÂ¤ÃŽÂµÃŽÂ»ÃŽÂµÃâ€¦Ãâ€žÃŽÂ±ÃŽÂ¯ÃŽÂ± ÃŽÂµÃŽÂ½ÃŽÂ·ÃŽÂ¼ÃŽÂ­ÃÂÃâ€°ÃÆ’ÃŽÂ· Ãâ‚¬ÃŽÂ¹ÃŽÂ½ÃŽÂ¬ÃŽÂºÃŽÂ±: 2025-10-01 (Ãâ‚¬ÃÂÃŽÂ¿ÃÆ’ÃŽÂµÃŽÂ³ÃŽÂ³ÃŽÂ¹ÃÆ’Ãâ€žÃŽÂ¹ÃŽÂºÃŽÂ¬ mid-market).

from typing import Optional, Tuple

# ÃŽÂ ÃÂÃŽÂ¿ÃÆ’ÃŽÂµÃŽÂ³ÃŽÂ³ÃŽÂ¹ÃÆ’Ãâ€žÃŽÂ¹ÃŽÂºÃŽÂ­Ãâ€š ÃŽÂ¹ÃÆ’ÃŽÂ¿Ãâ€žÃŽÂ¹ÃŽÂ¼ÃŽÂ¯ÃŽÂµÃâ€š -> USD
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
    # Ãâ‚¬ÃÂÃÅ’ÃÆ’ÃŽÂ¸ÃŽÂµÃÆ’ÃŽÂµ ÃŽÂ±ÃŽÂ½ Ãâ€¡ÃÂÃŽÂµÃŽÂ¹ÃŽÂ±ÃÆ’Ãâ€žÃŽÂµÃŽÂ¯Ãâ€š ÃŽÂºÃŽÂ¹ ÃŽÂ¬ÃŽÂ»ÃŽÂ»ÃŽÂ±
}

def to_usd_range(min_amount: Optional[float],
                 max_amount: Optional[float],
                 currency: Optional[str]) -> Optional[Tuple[float, float]]:
    """ÃŽÅ“ÃŽÂµÃâ€žÃŽÂ±Ãâ€žÃÂÃŽÂ­Ãâ‚¬ÃŽÂµÃŽÂ¹ Ãâ‚¬ÃÂÃŽÂ¿ÃŽÂ±ÃŽÂ¹ÃÂÃŽÂµÃâ€žÃŽÂ¹ÃŽÂºÃÅ’ range ÃÆ’ÃŽÂµ USD. ÃŽâ€¢Ãâ‚¬ÃŽÂ¹ÃÆ’Ãâ€žÃÂÃŽÂ­Ãâ€ ÃŽÂµÃŽÂ¹ (min_usd, max_usd) ÃŽÂ® None."""
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
    # ÃŽâ€˜ÃŽÂ½ ÃŽÂºÃŽÂ±ÃŽÂ¹ Ãâ€žÃŽÂ± ÃŽÂ´ÃÂÃŽÂ¿ None, ÃŽÂ´ÃŽÂµÃŽÂ½ Ãâ€žÃâ€¦Ãâ‚¬ÃÅ½ÃŽÂ½ÃŽÂ¿Ãâ€¦ÃŽÂ¼ÃŽÂµ Ãâ€žÃŽÂ¯Ãâ‚¬ÃŽÂ¿Ãâ€žÃŽÂ±
    if min_usd is None and max_usd is None:
        return None
    return (min_usd or 0.0, max_usd or 0.0)

def usd_line(min_amount: Optional[float],
             max_amount: Optional[float],
             currency: Optional[str]) -> Optional[str]:
    """ÃŽâ€¢Ãâ‚¬ÃŽÂ¹ÃÆ’Ãâ€žÃÂÃŽÂ­Ãâ€ ÃŽÂµÃŽÂ¹ Ãâ€žÃŽÂ·ÃŽÂ½ ÃŽÂ­Ãâ€žÃŽÂ¿ÃŽÂ¹ÃŽÂ¼ÃŽÂ· ÃŽÂ³ÃÂÃŽÂ±ÃŽÂ¼ÃŽÂ¼ÃŽÂ® Ãâ‚¬.Ãâ€¡. '~ $100.00Ã¢â‚¬â€œ$300.00 USD' ÃŽÂ® None."""
    rng = to_usd_range(min_amount, max_amount, currency)
    if not rng:
        return None
    lo, hi = rng
    if lo and hi:
        return f"~ ${lo:,.2f}Ã¢â‚¬â€œ${hi:,.2f} USD"
    if lo and not hi:
        return f"~ from ${lo:,.2f} USD"
    if hi and not lo:
        return f"~ up to ${hi:,.2f} USD"
    return None







