# utils.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

# Πόσες μέρες trial δίνουμε by default
DEFAULT_TRIAL_DAYS: int = 10

def now_utc() -> datetime:
    """Επιστρέφει τρέχουσα ώρα σε UTC (aware)."""
    return datetime.now(timezone.utc)

def _uid_field() -> Literal["telegram_id"]:
    """
    Το όνομα του πεδίου-κλειδιού χρήστη όπως είναι στο User model.
    Αν στο μέλλον αλλάξει, προσαρμόζουμε εδώ για να μη σπάσουν imports.
    """
    return "telegram_id"
