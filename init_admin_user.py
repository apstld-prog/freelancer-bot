# init_admin_user.py
from db import get_session
from sqlalchemy import text

ADMIN_ID = 5254014824
ADMIN_USERNAME = 'admin'

with get_session() as s:
    conn = s.connection()
    try:
        # Ελέγχουμε αν υπάρχει η στήλη 'role' ή 'is_admin' στον πίνακα
        check_cols = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name='user';
        """)).fetchall()
        col_names = [r[0] for r in check_cols]

        # Διαφορετικά SQL ανάλογα με τα πεδία
        if "role" in col_names:
            insert_sql = """
                INSERT INTO "user" (id, username, role, created_at)
                VALUES (:id, :username, 'admin', NOW() AT TIME ZONE 'UTC')
                ON CONFLICT (id) DO NOTHING;
            """
        elif "is_admin" in col_names:
            insert_sql = """
                INSERT INTO "user" (id, username, is_admin, created_at)
                VALUES (:id, :username, TRUE, NOW() AT TIME ZONE 'UTC')
                ON CONFLICT (id) DO NOTHING;
            """
        else:
            insert_sql = """
                INSERT INTO "user" (id, username, created_at)
                VALUES (:id, :username, NOW() AT TIME ZONE 'UTC')
                ON CONFLICT (id) DO NOTHING;
            """

        conn.execute(text(insert_sql), {"id": ADMIN_ID, "username": ADMIN_USERNAME})
        s.commit()
        print(f"✅ Admin user {ADMIN_ID} ensured in 'user' table.")

    except Exception as e:
        print(f"❌ Failed to ensure admin user: {e}")
