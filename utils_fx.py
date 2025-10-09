
import json
from typing import Optional

def load_fx_rates(env_value: str):
    if not env_value:
        return {"USD": 1.0, "EUR": 1.08, "GBP": 1.26}
    try:
        data = json.loads(env_value)
        if isinstance(data, dict) and data:
            return {k.upper(): float(v) for k, v in data.items()}
    except Exception:
        pass
    return {"USD": 1.0, "EUR": 1.08, "GBP": 1.26}

def to_usd(amount: Optional[float], ccy: Optional[str], rates: dict) -> Optional[float]:
    if amount is None or not ccy:
        return amount
    ccy = ccy.upper()
    rate = rates.get(ccy)
    if not rate:
        return amount
    try:
        return round(float(amount) * (1.0 / float(rate)), 2)
    except Exception:
        return amount
