import logging
from sqlalchemy import text
from db import get_session

logger = logging.getLogger("db_keywords")


# ---------------------------------------------------------
# Ensure keyword table exists
# ---------------------------------------------------------
def ensure_keywords_schema():
    """
    Ensures keyword table exists and has a consistent structure:
    id (PK), user_id (BIGINT), value (TEXT NOT NULL)
    """
    db = get_session()
    try:
        # Create table if missing
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS keyword (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                value TEXT NOT NULL
            );
        """))

        # Make sure column value exists and is NOT NULL
        db.execute(text("""
            ALTER TABLE keyword
            ALTER COLUMN value SET NOT NULL;
        """))

        # Index for fast lookup
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_keyword_user
            ON keyword (user_id);
        """))

        db.commit()
        logger.info("✅ keyword table ensured.")
    except Exception as e:
        db.rollback()
        logger.error(f"❌ ensure_keywords_schema failed: {e}")
    finally:
        db.close()


# ---------------------------------------------------------
# Get keywords for one user
# ---------------------------------------------------------
def get_keywords(user_id: int):
    """
    Returns a clean Python list of strings with the user's keywords.
    Example: ["logo", "led", "lighting"]
    """
    db = get_session()
    try:
        rows = db.execute(
            text("SELECT value FROM keyword WHERE user_id = :uid ORDER BY id ASC"),
            {"uid": user_id}
        ).fetchall()

        # Convert list of tuples → list of strings
        return [r[0].strip() for r in rows if r[0]]
    except Exception as e:
        logger.error(f"❌ get_keywords failed: {e}")
        return []
    finally:
        db.close()


# ---------------------------------------------------------
# Add keyword
# ---------------------------------------------------------
def add_keyword(user_id: int, value: str):
    db = get_session()
    try:
        db.execute(
            text("INSERT INTO keyword (user_id, value) VALUES (:u, :v)"),
            {"u": user_id, "v": value.strip()}
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"❌ add_keyword failed: {e}")
    finally:
        db.close()


# ---------------------------------------------------------
# Delete keyword
# ---------------------------------------------------------
def delete_keyword(user_id: int, value: str):
    db = get_session()
    try:
        db.execute(
            text("DELETE FROM keyword WHERE user_id = :u AND value = :v"),
            {"u": user_id, "v": value.strip()}
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"❌ delete_keyword failed: {e}")
    finally:
        db.close()

