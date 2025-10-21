# utils.py
from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Literal, List

DEFAULT_TRIAL_DAYS: int = 10

# ----------------------------------
# Γενικές βοηθητικές συναρτήσεις
# ----------------------------------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _uid_field() -> Literal["telegram_id"]:
    return "telegram_id"

# ----------------------------------
# Αρχεία δεδομένων
# ----------------------------------
USERS_FILE = "users.json"
KEYWORDS_FILE = "keywords.json"
SETTINGS_FILE = "settings.json"  # <── προστέθηκε

# ----------------------------------
# Χρήστες
# ----------------------------------
def load_users() -> dict:
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_users(users: dict):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def get_user(users: dict, telegram_id: int) -> dict:
    return users.get(str(telegram_id), {})

# ----------------------------------
# Λέξεις-Κλειδιά
# ----------------------------------
def load_keywords() -> List[str]:
    try:
        with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_keywords(keywords: List[str]):
    with open(KEYWORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(keywords, f, ensure_ascii=False, indent=2)

# ----------------------------------
# Έλεγχος Admin
# ----------------------------------
def is_admin(user_id: int) -> bool:
    ADMIN_IDS = [5254014824, 7916253053]
    return user_id in ADMIN_IDS

# ----------------------------------
# Μορφοποίηση Αγγελιών
# ----------------------------------
def format_jobs(jobs: list) -> str:
    if not jobs:
        return "⚠️ Δεν βρέθηκαν αγγελίες."

    formatted = []
    for job in jobs[:10]:
        title = job.get("title", "Χωρίς τίτλο")
        budget = job.get("budget", "—")
        link = job.get("link", "")
        formatted.append(f"🔹 <b>{title}</b>\n💰 {budget}\n🔗 {link}")

    return "\n\n".join(formatted)

# ----------------------------------
# Ρυθμίσεις (προστέθηκαν για το bot)
# ----------------------------------
def load_settings() -> dict:
    """Φορτώνει τις ρυθμίσεις από το settings.json (αν υπάρχει)."""
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_settings(settings: dict):
    """Αποθηκεύει τις ρυθμίσεις στο settings.json."""
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
