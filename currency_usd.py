import logging

logger = logging.getLogger(__name__)

# Simple conversion table
RATES = {
    "USD": 1.0,
    "EUR": 1.08,
    "GBP": 1.26,
    "AUD": 0.65,
    "CAD": 0.73,
    "INR": 0.012,
    "BRL": 0.18,
    "TRY": 0.032,
}

def convert_to_usd(amount, currency="USD"):
    """Converts given amount to USD based on predefined rates"""
    if amount is None:
        return None
    if not currency:
        currency = "USD"
    currency = currency.upper()
    rate = RATES.get(currency)
    if not rate:
        logger.warning(f"[convert_to_usd] Unknown currency: {currency}")
        return None
    try:
        return round(float(amount) * rate, 2)
    except Exception as e:
        logger.error(f"[convert_to_usd] Error: {e}")
        return None

def usd_line(amount, currency="USD"):
    """Returns formatted budget line with USD conversion in parentheses"""
    if not amount:
        return "N/A USD"
    usd_value = convert_to_usd(amount, currency)
    if usd_value:
        return f"{amount} {currency.upper()} ({usd_value} USD)"
    return f"{amount} {currency.upper()}"
