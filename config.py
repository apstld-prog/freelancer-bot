# config.py
import datetime

# Base URL for Freelancer
FREELANCER_URL = "https://www.freelancer.com"

# Static conversion rates
CURRENCY_TO_USD = {
    "USD": 1.0,
    "EUR": 1.08,
    "GBP": 1.27,
    "INR": 0.012,
    "AUD": 0.65,
    "CAD": 0.73,
    "SGD": 0.73,
}

def convert_to_usd(amount: float, currency: str) -> float:
    """Convert any known currency to USD."""
    rate = CURRENCY_TO_USD.get(currency.upper(), 1.0)
    return round(amount * rate, 2)

def posted_ago(dt: datetime.datetime) -> str:
    """Return human readable time difference."""
    if not dt:
        return "just now"
    diff = datetime.datetime.utcnow() - dt
    mins = int(diff.total_seconds() / 60)
    if mins < 1:
        return "just now"
    elif mins < 60:
        return f"{mins} min ago"
    hours = mins // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"
