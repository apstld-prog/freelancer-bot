import logging
from db import get_connection

logger = logging.getLogger(__name__)

def get_user_keywords(user_id: int):
    """
    Returns a list of keywords for a given user.
    Works even if user_keywords table does not exist.
    """
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
            keywords = [r[0] for r in rows]
            logger.info(f"[get_user_keywords] Loaded from user_keywords: {keywords}")
            return keywords

        # Fallback to 'users' table keywords column
        cur.execute("SELECT keywords FROM users WHERE id = %s;", (user_id,))
        row = cur.fetchone()
        if row and row[0]:
            keywords = [k.strip() for k in row[0].split(',') if k.strip()]
            logger.info(f"[get_user_keywords] Loaded from users.keywords: {keywords}")
            return keywords

        return []
    except Exception as e:
        logger.error(f"[get_user_keywords] Error: {e}")
        return []
    finally:
        if 'conn' in locals():
            conn.close()

def get_all_user_keywords():
    """
    Returns {user_id: [keywords]} for all users.
    """
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

        logger.info(f"[get_all_user_keywords] Loaded {len(users_keywords)} users")
        return users_keywords
    except Exception as e:
        logger.error(f"[get_all_user_keywords] Error: {e}")
        return {}
    finally:
        if 'conn' in locals():
            conn.close()
