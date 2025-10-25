import os
import psycopg2
from psycopg2.extras import DictCursor

def get_db_connection():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"), cursor_factory=DictCursor)
    return conn

def get_user_list():
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT user_id, keywords FROM user_settings WHERE active = TRUE;")
        rows = cur.fetchall()
    conn.close()
    users = []
    for row in rows:
        uid = row["user_id"]
        kws = [k.strip() for k in (row["keywords"] or "").split(",") if k.strip()]
        if kws:
            users.append((uid, kws))
    return users
