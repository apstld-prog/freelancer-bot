# utils.py

from config import ADMIN_IDS
from db import get_session, get_or_create_user_by_tid

def is_admin_user(user_id: int) -> bool:
    try:
        return int(user_id) in ADMIN_IDS
    except:
        return False

def ensure_user(telegram_id: int):
    session = get_session()
    user = get_or_create_user_by_tid(session, telegram_id)
    session.close()
    return user
