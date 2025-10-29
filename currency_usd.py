import logging

logger = logging.getLogger("currency_usd")

# Simple fixed-rate USD converter (extendable)
def convert_to_usd(amount, currency="USD"):
    """Convert any supported currency to USD using approximate static rates."""
    if amount is None:
        return None
    try:
        currency = (currency or "USD").upper()
        if currency == "USD":
            return float(amount)
        elif currency == "EUR":
            return float(amount) * 1.07
        elif currency == "GBP":
            return float(amount) * 1.26
        elif currency == "AUD":
            return float(amount) * 0.65
        elif currency == "CAD":
            return float(amount) * 0.73
        elif currency == "INR":
            return float(amount) * 0.012
        elif currency == "PLN":
            return float(amount) * 0.25
        elif currency == "CHF":
            return float(amount) * 1.10
        elif currency == "SEK":
            return float(amount) * 0.092
        elif currency == "NOK":
            return float(amount) * 0.089
        else:
            logger.warning(f"[convert_to_usd] Unknown currency '{currency}', keeping as-is")
            return float(amount)
    except Exception as e:
        logger.error(f"[convert_to_usd] Conversion error: {e}")
        return amount


# ✅ Helper line for display formatting
def usd_line(amount, currency="USD"):
    """Return formatted string line for Telegram message."""
    try:
        if amount is None:
            return "💲 Budget: N/A"
        usd_value = convert_to_usd(amount, currency)
        if usd_value is None:
            return "💲 Budget: N/A"
        return f"💲 Budget: {amount} {currency} ≈ {usd_value:.2f} USD"
    except Exception:
        return "💲 Budget: N/A"
