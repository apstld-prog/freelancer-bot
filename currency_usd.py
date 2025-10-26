import logging

logger = logging.getLogger("currency_usd")

# Σταθερές ισοτιμίες για τα πιο συχνά νομίσματα
USD_EXCHANGE = {
    "USD": 1.0,
    "EUR": 1.07,
    "GBP": 1.25,
    "AUD": 0.66,
    "CAD": 0.73,
    "CHF": 1.11,
    "JPY": 0.0064,
    "NOK": 0.091,
    "SEK": 0.092,
    "PLN": 0.25,
    "INR": 0.012,
    "TRY": 0.030,
    "AED": 0.27,
    "RUB": 0.010,
    "MXN": 0.056,
    "DKK": 0.14,
    "CZK": 0.043,
    "HUF": 0.0027,
    "ZAR": 0.055,
    "NZD": 0.60
}

def convert_to_usd(amount, currency):
    """
    Μετατρέπει ένα ποσό από το δοσμένο νόμισμα σε USD.
    Αν το νόμισμα δεν υπάρχει στις ισοτιμίες, επιστρέφει το ίδιο ποσό.
    """
    if not amount or not currency:
        return "N/A"

    try:
        amount = float(amount)
        currency = currency.upper().strip()
        rate = USD_EXCHANGE.get(currency)

        if not rate:
            logger.warning(f"Unknown currency '{currency}', returning raw value.")
            return round(amount, 2)

        return round(amount * rate, 2)
    except Exception as e:
        logger.error(f"[convert_to_usd] Error converting {amount} {currency}: {e}")
        return "N/A"


# Προαιρετική λειτουργία δοκιμής
if __name__ == "__main__":
    print(convert_to_usd(100, "EUR"))   # 107.0
    print(convert_to_usd(50, "GBP"))    # 62.5
    print(convert_to_usd(1000, "JPY"))  # 6.4
    print(convert_to_usd(100, "XYZ"))   # 100.0 (άγνωστο νόμισμα)
