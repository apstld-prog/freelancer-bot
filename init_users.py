# ======================================================
# init_users.py — ensure admin user and default users
# ======================================================
import logging
from sqlalchemy import text
from db import get_session

logger = logging.getLogger("init_users")

def ensure_admin_user(admin_id: int = 1, tg_id: int = 5254014824, username: str = "admin"):
    """Ensure that the admin user exists in both 'user' and 'users' tables."""
    queries = {
        "user": text("""
            INSERT INTO "user" (id, telegram_id, username, is_admin, is_active, created_at)
            VALUES (:id, :tg, :username, TRUE, TRUE, NOW() AT TIME ZONE 'UTC')
            ON CONFLICT (id) DO UPDATE
            SET telegram_id = EXCLUDED.telegram_id,
                username = EXCLUDED.username,
                is_admin = TRUE,
                is_active = TRUE;
        """),
        "users": text("""
            INSERT INTO users (id, telegram_id, username, is_admin, is_active, created_at)
            VALUES (:id, :tg, :username, TRUE, TRUE, NOW() AT TIME ZONE 'UTC')
            ON CONFLICT (id) DO UPDATE
            SET telegram_id = EXCLUDED.telegram_id,
                username = EXCLUDED.username,
                is_admin = TRUE,
                is_active = TRUE;
        """)
    }

    with get_session() as s:
        tables = [r[0] for r in s.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
        ).fetchall()]

        logger.info("✅ Found user-related tables: %s", tables)
        for tbl in ("user", "users"):
            if tbl in tables:
                logger.info(f"📊 Ensuring admin in table: {tbl}")
                try:
                    s.execute(queries[tbl], {"id": admin_id, "tg": tg_id, "username": username})
                    s.commit()
                    logger.info(f"✅ Admin ensured in '{tbl}' successfully.")
                except Exception as e:
                    s.rollback()
                    logger.warning(f"⚠️ Failed to ensure admin in '{tbl}': {e}")
        logger.info("======================================================")
        logger.info("✅ init_users complete — admin synchronized in all tables.")
        logger.info("======================================================")

if __name__ == "__main__":
    ensure_admin_user()
