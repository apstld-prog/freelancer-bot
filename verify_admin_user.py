from sqlalchemy import create_engine, text
import os

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("❌ DATABASE_URL not found.")
    exit(1)

engine = create_engine(db_url)

ADMIN_ID = 5254014824

with engine.connect() as conn:
    res = conn.execute(text("""
        SELECT id, telegram_id, is_admin, is_active, started_at
        FROM users
        WHERE telegram_id = :tid;
    """), {"tid": ADMIN_ID}).fetchone()

    if not res:
        print("❌ Admin user not found.")
    else:
        print("✅ Admin user record found:")
        print(res)

        # Ensure proper flags
        conn.execute(text("""
            UPDATE users
            SET is_admin = TRUE, is_active = TRUE
            WHERE telegram_id = :tid;
        """), {"tid": ADMIN_ID})
        conn.commit()
        print("🔧 Updated is_admin=True and is_active=True.")
