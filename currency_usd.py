# currency_usd.py
# Drop-in helper for showing "~ $min–$max USD" lines.
# Δεν έχει εξωτερικά dependencies. Rates είναι conservative,
# με fallback σε 1:1 αν δεν βρεθεί νόμισμα (οπότε απλά δεν θα τυπώσει USD).
# Τελευταία ενημέρωση πινάκα: 2025-10-01 (προσεγγιστικά mid-market).

from typing import Optional, Tuple

# Προσεγγιστικές ισοτιμίες -> USD
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
    # πρόσθεσε αν χρειαστείς κι άλλα
}

def to_usd_range(min_amount: Optional[float],
                 max_amount: Optional[float],
                 currency: Optional[str]) -> Optional[Tuple[float, float]]:
    """Μετατρέπει προαιρετικό range σε USD. Επιστρέφει (min_usd, max_usd) ή None."""
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
    # Αν και τα δύο None, δεν τυπώνουμε τίποτα
    if min_usd is None and max_usd is None:
        return None
    return (min_usd or 0.0, max_usd or 0.0)

def usd_line(min_amount: Optional[float],
             max_amount: Optional[float],
             currency: Optional[str]) -> Optional[str]:
    """Επιστρέφει την έτοιμη γραμμή π.χ. '~ $100.00–$300.00 USD' ή None."""
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
