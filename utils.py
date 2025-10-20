# utils.py
from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Literal, List

# Πόσες μέρες trial δίνουμε by default
DEFAULT_TRIAL_DAYS: int = 10

# ----------------------------------
# Γενικές βοηθητικές συναρτήσεις
# ----------------------------------

def now_utc() -> datetime:
    """Επιστρέφει τρέχουσα ώρα σε UTC (aware)."""
    return datetime.now(timezone.utc)

def _uid_field() -> Literal["telegram_id"]:
    """Το όνομα του πεδίου-κλειδιού χρήστη."""
    return "telegram_id"

# ----------------------------------
# Αρχεία δεδομένων
# ----------------------------------
USERS_FILE = "users.json"
KEYWORDS_FILE = "keywords.json"

# ----------------------------------
# Χρήστες
# ----------------------------------
def load_users() -> dict:
    """Φορτώνει τους χρήστες από users.json (αν υπάρχει)."""
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_users(users: dict):
    """Αποθηκεύει τους χρήστες στο users.json."""
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def get_user(users: dict, telegram_id: int) -> dict:
    """Επιστρέφει τα δεδομένα ενός χρήστη, αν υπάρχει."""
    return users.get(str(telegram_id), {})

# ----------------------------------
# Λέξεις-Κλειδιά
# ----------------------------------
def load_keywords() -> List[str]:
    """Φορτώνει τις λέξεις-κλειδιά από keywords.json."""
    try:
        with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_keywords(keywords: List[str]):
    """Αποθηκεύει τις λέξεις-κλειδιά στο keywords.json."""
    with open(KEYWORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(keywords, f, ensure_ascii=False, indent=2)

# ----------------------------------
# Έλεγχος Admin
# ----------------------------------
def is_admin(user_id: int) -> bool:
    """Επιστρέφει True αν ο χρήστης είναι admin (σταθερός ID)."""
    ADMIN_IDS = [5254014824, 7916253053]  # μπορείς να προσθέσεις κι άλλους
    return user_id in ADMIN_IDS

# ----------------------------------
# Μορφοποίηση Αγγελιών
# ----------------------------------
def format_jobs(jobs: list) -> str:
    """Επιστρέφει τις αγγελίες σε μορφή κειμένου για το Telegram."""
    if not jobs:
        return "⚠️ Δεν βρέθηκαν αγγελίες."

    formatted = []
    for job in jobs[:10]:  # στέλνουμε τις πρώτες 10 για καθαρό μήνυμα
        title = job.get("title", "Χωρίς τίτλο")
        budget = job.get("budget", "—")
        link = job.get("link", "")
        formatted.append(f"🔹 <b>{title}</b>\n💰 {budget}\n🔗 {link}")

    return "\n\n".join(formatted)
