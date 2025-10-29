import logging
from db import get_connection

logger = logging.getLogger(__name__)

# ======================================================
# 🔹 Get keywords for one user
# ======================================================
def get_user_keywords(user_id: int):
    """Return all keywords for a specific user."""
    try:
        conn = get_connection()
        cur = conn.cursor()

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


# ======================================================
# 🔹 Get keywords for all users
# ======================================================
def get_all_user_keywords():
    """Return {user_id: [keywords]} for all users."""
    users_keywords = {}
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, keywords FROM users WHERE keywords IS NOT NULL;")
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


# ======================================================
# 🔹 Add new keywords for a user
# ======================================================
def add_keywords(user_id: int, new_keywords: list[str]):
    """Add new keywords to an existing user (avoids duplicates)."""
    if not new_keywords:
        return 0

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT keywords FROM users WHERE id = %s;", (user_id,))
        row = cur.fetchone()

        existing = []
        if row and row[0]:
            existing = [k.strip().lower() for k in row[0].split(',') if k.strip()]

        added = []
        for kw in new_keywords:
            kw_norm = kw.strip().lower()
            if kw_norm and kw_norm not in existing:
                existing.append(kw_norm)
                added.append(kw_norm)

        cur.execute("UPDATE users SET keywords = %s WHERE id = %s;", (",".join(existing), user_id))
        conn.commit()
        logger.info(f"[add_keywords] ✅ Added {len(added)} keywords for user {user_id}")
        return len(added)
    except Exception as e:
        logger.error(f"[add_keywords] Error: {e}")
        return 0
    finally:
        if 'conn' in locals():
            conn.close()


# ======================================================
# 🔹 Delete one or more keywords from a user
# ======================================================
def delete_keywords(user_id: int, keywords_to_delete: list[str]):
    """Remove one or more keywords from a user's list."""
    if not keywords_to_delete:
        return 0

    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT keywords FROM users WHERE id = %s;", (user_id,))
        row = cur.fetchone()
        if not row or not row[0]:
            return 0

        current = [k.strip().lower() for k in row[0].split(',') if k.strip()]
        to_remove = [k.strip().lower() for k in keywords_to_delete if k.strip()]

        updated = [k for k in current if k not in to_remove]
        removed_count = len(current) - len(updated)

        cur.execute("UPDATE users SET keywords = %s WHERE id = %s;", (",".join(updated), user_id))
        conn.commit()

        logger.info(f"[delete_keywords] 🗑️ Removed {removed_count} keywords from user {user_id}")
        return removed_count
    except Exception as e:
        logger.error(f"[delete_keywords] Error: {e}")
        return 0
    finally:
        if 'conn' in locals():
            conn.close()


# ======================================================
# 🔹 List all distinct keywords
# ======================================================
def list_keywords():
    """Return all distinct keywords from user_keywords or users.keywords."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'user_keywords'
            );
        """)
        exists = cur.fetchone()[0]

        if exists:
            cur.execute("SELECT DISTINCT keyword FROM user_keywords;")
            rows = cur.fetchall()
            return [r[0] for r in rows if r[0]]

        cur.execute("SELECT DISTINCT keywords FROM users WHERE keywords IS NOT NULL;")
        all_kw = set()
        for (kw_str,) in cur.fetchall():
            if kw_str:
                all_kw.update([k.strip() for k in kw_str.split(',') if k.strip()])
        return list(all_kw)
    except Exception as e:
        logger.error(f"[list_keywords] Error: {e}")
        return []
    finally:
        if 'conn' in locals():
            conn.close()


# ======================================================
# 🔹 Count keywords
# ======================================================
def count_keywords():
    """Return total number of unique keywords."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'user_keywords'
            );
        """)
        exists = cur.fetchone()[0]

        if exists:
            cur.execute("SELECT COUNT(DISTINCT keyword) FROM user_keywords;")
            total = cur.fetchone()[0]
            return total or 0

        cur.execute("SELECT keywords FROM users WHERE keywords IS NOT NULL;")
        all_kw = set()
        for (kw_str,) in cur.fetchall():
            if kw_str:
                all_kw.update([k.strip() for k in kw_str.split(',') if k.strip()])
        return len(all_kw)
    except Exception as e:
        logger.error(f"[count_keywords] Error: {e}")
        return 0
    finally:
        if 'conn' in locals():
            conn.close()


# ======================================================
# 🔹 Ensure unique keyword in global table
# ======================================================
def ensure_keyword_unique(keyword: str):
    """Ensure keyword exists only once in user_keywords table."""
    if not keyword:
        return False

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'user_keywords'
            );
        """)
        exists = cur.fetchone()[0]

        if not exists:
            logger.warning("[ensure_keyword_unique] user_keywords table not found.")
            return False

        cur.execute("SELECT COUNT(*) FROM user_keywords WHERE keyword = %s;", (keyword,))
        count = cur.fetchone()[0]
        if count == 0:
            cur.execute("INSERT INTO user_keywords (user_id, keyword) VALUES (1, %s);", (keyword,))
            conn.commit()
            logger.info(f"[ensure_keyword_unique] ✅ Added new keyword '{keyword}'")
            return True

        logger.info(f"[ensure_keyword_unique] Keyword '{keyword}' already exists")
        return False
    except Exception as e:
        logger.error(f"[ensure_keyword_unique] Error: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()
