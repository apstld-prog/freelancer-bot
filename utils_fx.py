import math

# --- Fixed currency conversion table ---
CURRENCY_TO_USD = {
    "USD": 1.0,
    "EUR": 1.08,
    "GBP": 1.27,
    "CAD": 0.73,
    "AUD": 0.66,
    "CHF": 1.11,
    "JPY": 0.0064,
    "INR": 0.012,
    "PLN": 0.25,
    "TRY": 0.033,
}

def convert_to_usd(amount, currency: str) -> float:
    """Convert given amount to USD using fixed table."""
    if not amount or not currency:
        return 0.0
    rate = CURRENCY_TO_USD.get(currency.upper(), 1.0)
    return round(float(amount) * rate, 2)

def format_budget(amount, currency):
    """Return formatted budget string with USD equivalent."""
    if not amount or not currency:
        return "Budget: N/A"
    usd = convert_to_usd(amount, currency)
    return f"Ã°Å¸â€™Â° <b>Budget:</b> {amount} {currency.upper()} (~${usd} USD)"

def posted_ago(created_dt, now_dt):
    """Return time difference in human-readable form."""
    if not created_dt:
        return ""
    delta = now_dt - created_dt
    seconds = delta.total_seconds()
    if seconds < 60:
        return f"{int(seconds)} seconds ago"
    elif seconds < 3600:
        return f"{int(seconds // 60)} minutes ago"
    elif seconds < 86400:
        return f"{int(seconds // 3600)} hours ago"
    else:
        return f"{int(seconds // 86400)} days ago"







