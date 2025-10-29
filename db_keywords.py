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
# 🔹 Add new keywords
# ======================================================
def add_keywords(user_id: int, new_keywords: list[str]):
    """Add new keywords for a user (avoids duplicates)."""
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
# 🔹 Delete specific keywords
# ======================================================
def delete_keywords(user_id: int, keywords_to_delete: list[str]):
    """Remove specific keywords from a user's list."""
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
# 🔹 Clear all keywords for a user
# ======================================================
def clear_keywords(user_id: int = None):
    """Remove all keywords for a specific user, or for all users if None."""
    try:
        conn = get_connection()
        cur = conn.cursor()

        if user_id:
            cur.execute("UPDATE users SET keywords = NULL WHERE id = %s;", (user_id,))
            logger.info(f"[clear_keywords] Cleared keywords for user {user_id}")
        else:
            cur.execute("UPDATE users SET keywords = NULL;")
            logger.info("[clear_keywords] Cleared keywords for ALL users")

        conn.commit()
        return True
    except Exception as e:
        logger.error(f"[clear_keywords] Error: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()


# ======================================================
# 🔹 List all keywords
# ======================================================
def list_keywords(user_id: int = None):
    """Return all distinct keywords globally or for a specific user."""
    try:
        conn = get_connection()
        cur = conn.cursor()

        if user_id:
            cur.execute("SELECT keywords FROM users WHERE id = %s;", (user_id,))
            row = cur.fetchone()
            if not row or not row[0]:
                return []
            return [k.strip() for k in row[0].split(',') if k.strip()]

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
# 🔹 Count total keywords
# ======================================================
def count_keywords(user_id: int = None):
    """Return total number of unique keywords globally or for a user."""
    try:
        conn = get_connection()
        cur = conn.cursor()

        if user_id:
            cur.execute("SELECT keywords FROM users WHERE id = %s;", (user_id,))
            row = cur.fetchone()
            if not row or not row[0]:
                return 0
            kw_list = [k.strip() for k in row[0].split(',') if k.strip()]
            return len(set(kw_list))

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
# 🔹 Ensure keyword is globally unique (safe for no-arg call)
# ======================================================
def ensure_keyword_unique(keyword: str = None):
    """
    Ensure keyword exists only once (used for admin seed).
    If called with no args, it simply ensures that the admin has some defaults.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()

        # if called with a specific keyword
        if keyword:
            cur.execute("SELECT keywords FROM users WHERE id = 1;")
            row = cur.fetchone()
            existing = []
            if row and row[0]:
                existing = [k.strip().lower() for k in row[0].split(',') if k.strip()]
            if keyword.lower() not in existing:
                existing.append(keyword.lower())
                cur.execute("UPDATE users SET keywords = %s WHERE id = 1;", (",".join(existing),))
                conn.commit()
                logger.info(f"[ensure_keyword_unique] ✅ Added keyword '{keyword}'")
                return True
            return False

        # if called without argument (during startup)
        cur.execute("SELECT keywords FROM users WHERE id = 1;")
        row = cur.fetchone()
        if not row or not row[0]:
            defaults = ["logo", "lighting", "sales"]
            cur.execute("UPDATE users SET keywords = %s WHERE id = 1;", (",".join(defaults),))
            conn.commit()
            logger.info("[ensure_keyword_unique] ✅ Added default keywords for admin")
            return True

        logger.info("[ensure_keyword_unique] Admin already has keywords, nothing added.")
        return True

    except Exception as e:
        logger.error(f"[ensure_keyword_unique] Error: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()
