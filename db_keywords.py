import logging
from db import get_connection

logger = logging.getLogger(__name__)

def get_user_keywords(user_id: int):
    """Return all keywords for a specific user."""
    try:
        conn = get_connection()
        cur = conn.cursor()

        # Check if user_keywords table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'user_keywords'
            );
        """)
        exists = cur.fetchone()[0]

        if exists:
            cur.execute("SELECT keyword FROM user_keywords WHERE user_id = %s;", (user_id,))
            rows = cur.fetchall()
            return [r[0] for r in rows]

        # fallback to 'users' table
        cur.execute("SELECT keywords FROM users WHERE id = %s;", (user_id,))
        row = cur.fetchone()
        if row and row[0]:
            return [k.strip() for k in row[0].split(',') if k.strip()]

        return []
    except Exception as e:
        logger.error(f"[get_user_keywords] Error: {e}")
        return []
    finally:
        if 'conn' in locals():
            conn.close()


def get_all_user_keywords():
    """Return {user_id: [keywords]} for all users."""
    users_keywords = {}
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, keywords FROM users WHERE keywords IS NOT NULL;
        """)
        for user_id, keywords_str in cur.fetchall():
            keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
            users_keywords[user_id] = keywords
        return users_keywords
    except Exception as e:
        logger.error(f"[get_all_user_keywords] Error: {e}")
        return {}
    finally:
        if 'conn' in locals():
            conn.close()


# ✅ Add missing function for bot.py compatibility
def list_keywords():
    """Legacy helper required by bot.py"""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT keyword FROM user_keywords;")
        rows = cur.fetchall()
        return [r[0] for r in rows if r[0]]
    except Exception as e:
        logger.error(f"[list_keywords] Error: {e}")
        return []
    finally:
        if 'conn' in locals():
            conn.close()
