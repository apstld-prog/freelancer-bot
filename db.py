import psycopg2
import os

def get_connection():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    conn.autocommit = True
    return conn

def get_user_list():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT user_id, keywords FROM user_settings WHERE active = TRUE;")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [{"user_id": r[0], "keywords": r[1].split(",")} for r in rows]
    except Exception as e:
        print("[DB] get_user_list error:", e)
        return []

# ------------------------------------------------------
# Compatibility helper for bot.py
# ------------------------------------------------------
def get_or_create_user_by_tid(tid: int):
    """Fallback helper to ensure bot.py can run without breaking imports."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM user_settings WHERE user_id = %s;", (tid,))
        user = cur.fetchone()
        if not user:
            cur.execute(
                "INSERT INTO user_settings (user_id, active, keywords) VALUES (%s, TRUE, '');",
                (tid,),
            )
        cur.close()
        conn.close()
        return {"user_id": tid}
    except Exception as e:
        print("[DB] get_or_create_user_by_tid error:", e)
        return {"user_id": tid}
