# init_admin_user.py
from db import get_session
from sqlalchemy import text

ADMIN_ID = 5254014824  # your Telegram ID (admin)
ADMIN_USERNAME = 'admin'
ADMIN_ROLE = 'admin'

with get_session() as s:
    conn = s.connection()
    try:
        conn.execute(text("""
            INSERT INTO "user" (id, username, role, created_at)
            VALUES (:id, :username, :role, NOW() AT TIME ZONE 'UTC')
            ON CONFLICT (id) DO NOTHING;
        """), {"id": ADMIN_ID, "username": ADMIN_USERNAME, "role": ADMIN_ROLE})
        s.commit()
        print(f"✅ Admin user {ADMIN_ID} ensured.")
    except Exception as e:
        print(f"❌ Failed to ensure admin user: {e}")
