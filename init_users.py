import os
from db import get_session

def ensure_admin_user():
    """Ensures admin user (id=1) exists"""
    admin_tid = os.getenv("ADMIN_TELEGRAM_ID", "5254014824")

    with get_session() as s:
        s.execute("""
        CREATE TABLE IF NOT EXISTS "user" (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE,
            username TEXT,
            is_admin BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            is_blocked BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW() NOT NULL
        );
        """)
        s.execute('SELECT * FROM "user" WHERE id=1;')
        existing = s.fetchone()

        if not existing:
            s.execute(
                'INSERT INTO "user" (id, telegram_id, username, is_admin, is_active, created_at, updated_at) '
                'VALUES (1, %s, %s, TRUE, TRUE, NOW(), NOW());',
                (admin_tid, "admin")
            )
            print("✅ Created admin user.")
        else:
            s.execute(
                'UPDATE "user" SET is_admin=TRUE, is_active=TRUE, updated_at=NOW() WHERE id=1;'
            )
            print("✅ Admin user already exists and active.")
        s.commit()


if __name__ == "__main__":
    print("====================================================")
    print("🔧 AUTO-FIX: ADMIN USER IN POSTGRES DATABASE")
    print("====================================================")
    ensure_admin_user()
    print("====================================================")
    print("✅ ADMIN USER FIX COMPLETED SUCCESSFULLY")
    print("====================================================")
