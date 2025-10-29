import logging

logger = logging.getLogger("currency_usd")

# Αν δεν βρεθεί νόμισμα ή rate, θα επιστραφεί ίδια τιμή
DEFAULT_RATES = {
    "USD": 1.0,
    "EUR": 1.08,
    "GBP": 1.28,
    "AUD": 0.66,
    "CAD": 0.73,
    "INR": 0.012,
    "PHP": 0.017,
}


def convert_to_usd(amount, currency="USD"):
    """Μετατρέπει ποσό στο ισοδύναμο USD με βάση σταθερούς συντελεστές."""
    if amount is None:
        return None
    try:
        rate = DEFAULT_RATES.get(currency.upper(), 1.0)
        return round(float(amount) * rate, 2)
    except Exception as e:
        logger.error(f"[convert_to_usd] Error: {e}")
        return amount


def usd_line(min_amount=None, max_amount=None, currency="USD"):
    """
    Δημιουργεί γραμμή π.χ. '$50 – $120 USD (≈ 100.00 USD)'
    με σωστή μετατροπή και όμορφη μορφοποίηση.
    """
    try:
        if not min_amount and not max_amount:
            return "Budget: N/A"

        if min_amount and not max_amount:
            usd = convert_to_usd(min_amount, currency)
            return f"💰 Budget: {min_amount:.0f} {currency} (≈ ${usd:.0f} USD)"

        if max_amount and not min_amount:
            usd = convert_to_usd(max_amount, currency)
            return f"💰 Budget: {max_amount:.0f} {currency} (≈ ${usd:.0f} USD)"

        # Αν έχουμε και min και max
        avg = (float(min_amount) + float(max_amount)) / 2
        usd = convert_to_usd(avg, currency)
        return f"💰 Budget: {min_amount:.0f}–{max_amount:.0f} {currency} (≈ ${usd:.0f} USD)"
    except Exception as e:
        logger.error(f"[usd_line] Error: {e}")
        return "Budget: N/A"
