from db import get_session
import os

def ensure_admin_user():
    admin_tid = os.getenv("ADMIN_TELEGRAM_ID", "5254014824")

    with get_session() as s:
        s.execute("""
        CREATE TABLE IF NOT EXISTS user (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE,
            username TEXT,
            is_admin BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            is_blocked BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
        """)
        s.execute("SELECT * FROM user WHERE telegram_id=%s;", (admin_tid,))
        existing = s.fetchone()
        if not existing:
            s.execute(
                "INSERT INTO user (telegram_id, username, is_admin, is_active, created_at, updated_at) "
                "VALUES (%s, 'admin', TRUE, TRUE, NOW(), NOW());",
                (admin_tid,)
            )
            print("✅ Created admin user.")
        else:
            s.execute(
                "UPDATE user SET is_admin=TRUE, is_active=TRUE, updated_at=NOW() WHERE telegram_id=%s;",
                (admin_tid,)
            )
            print("✅ Admin user already exists and active.")

        s.commit()


if __name__ == "__main__":
    print("====================================================")
    print("🔧 INIT ADMIN USER TOOL")
    print("====================================================")
    ensure_admin_user()
    print("====================================================")
    print("✅ ADMIN USER CREATED / UPDATED SUCCESSFULLY")
    print("====================================================")
