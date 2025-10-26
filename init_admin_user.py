# init_admin_user.py
from db import get_session
from sqlalchemy import text

ADMIN_ID = 5254014824
ADMIN_USERNAME = 'admin'

with get_session() as s:
    conn = s.connection()
    try:
        # --- Step 1: εντοπισμός του σωστού πίνακα ---
        table_check = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_name ILIKE 'user%' AND table_schema='public';
        """)).fetchall()
        tables = [r[0] for r in table_check]
        print(f"🧩 Found user-related tables: {tables}")

        if not tables:
            print("❌ No table named user or users found. Cannot continue.")
            exit(1)

        table_name = tables[0]

        # --- Step 2: εμφάνιση των στηλών ---
        col_check = conn.execute(text(f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_name='{table_name}';
        """)).fetchall()
        cols = [r[0] for r in col_check]
        print(f"📊 Columns in table '{table_name}': {cols}")

        # --- Step 3: δημιουργία admin user ανάλογα με το schema ---
        if "role" in cols:
            insert_sql = f"""
                INSERT INTO "{table_name}" (id, username, role, created_at)
                VALUES (:id, :username, 'admin', NOW() AT TIME ZONE 'UTC')
                ON CONFLICT (id) DO NOTHING;
            """
        elif "is_admin" in cols:
            insert_sql = f"""
                INSERT INTO "{table_name}" (id, username, is_admin, created_at)
                VALUES (:id, :username, TRUE, NOW() AT TIME ZONE 'UTC')
                ON CONFLICT (id) DO NOTHING;
            """
        elif "created_at" in cols:
            insert_sql = f"""
                INSERT INTO "{table_name}" (id, username, created_at)
                VALUES (:id, :username, NOW() AT TIME ZONE 'UTC')
                ON CONFLICT (id) DO NOTHING;
            """
        else:
            insert_sql = f"""
                INSERT INTO "{table_name}" (id, username)
                VALUES (:id, :username)
                ON CONFLICT (id) DO NOTHING;
            """

        conn.execute(text(insert_sql), {"id": ADMIN_ID, "username": ADMIN_USERNAME})
        s.commit()
        print(f"✅ Admin user {ADMIN_ID} ensured in '{table_name}' table.")

    except Exception as e:
        print(f"❌ Failed to ensure admin user: {e}")
