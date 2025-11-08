from db import get_session, get_or_create_user_by_tid

def get_or_create_user(tid: int):
    return get_or_create_user_by_tid(tid)
