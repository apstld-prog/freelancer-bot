# utils.py
from __future__ import annotations
import json
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

# -----------------------------
# ΝΕΕΣ ΣΥΝΑΡΤΗΣΕΙΣ για bot.py
# -----------------------------

USERS_FILE = "users.json"

def load_users() -> dict:
    """Φορτώνει τους χρήστες από users.json (αν υπάρχει)."""
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}

def save_users(users: dict):
    """Αποθηκεύει τους χρήστες στο users.json."""
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def get_user(users: dict, telegram_id: int) -> dict:
    """Επιστρέφει τα δεδομένα ενός χρήστη, αν υπάρχει."""
    return users.get(str(telegram_id), {})
