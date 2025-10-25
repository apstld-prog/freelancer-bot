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
