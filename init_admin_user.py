# ======================================================
# init_admin_user.py — robust admin user initializer
# ======================================================
from db import get_session
from sqlalchemy import text

ADMIN_ID = 5254014824
ADMIN_USERNAME = "admin"

print("[Init] Ensuring admin user...")

with get_session() as s:
    conn = s.connection()
    try:
        # Step 1 — Locate correct table
        table_check = conn.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name ILIKE 'user%' AND table_schema='public';
        """)).fetchall()
        tables = [r[0] for r in table_check]
        print(f"🧩 Found user-related tables: {tables}")

        if not tables:
            print("❌ No table named 'user' or 'users' found. Cannot continue.")
            exit(1)

        table_name = tables[0]

        # Step 2 — Inspect columns
        col_check = conn.execute(text(f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_name='{table_name}';
        """)).fetchall()
        cols = [r[0] for r in col_check]
        print(f"📊 Columns in table '{table_name}': {cols}")

        # Step 3 — Build adaptive INSERT based on schema
        fields = []
        values = []
        updates = []

        # Always insert id, telegram_id, username
        if "id" in cols:
            fields.append("id")
            values.append(":id")
        if "telegram_id" in cols:
            fields.append("telegram_id")
            values.append(":tg")
            updates.append("telegram_id = EXCLUDED.telegram_id")
        if "username" in cols:
            fields.append("username")
            values.append(":username")
            updates.append("username = EXCLUDED.username")

        # Optional flags
        if "is_admin" in cols:
            fields.append("is_admin")
            values.append("TRUE")
            updates.append("is_admin = TRUE")
        if "is_active" in cols:
            fields.append("is_active")
            values.append("TRUE")
            updates.append("is_active = TRUE")
        if "is_blocked" in cols:
            fields.append("is_blocked")
            values.append("FALSE")
            updates.append("is_blocked = FALSE")

        # Timestamp columns
        if "created_at" in cols:
            fields.append("created_at")
            values.append("NOW() AT TIME ZONE 'UTC'")
        if "updated_at" in cols:
            fields.append("updated_at")
            values.append("NOW() AT TIME ZONE 'UTC'")

        # Build final SQL dynamically
        insert_sql = f"""
            INSERT INTO "{table_name}" ({', '.join(fields)})
            VALUES ({', '.join(values)})
            ON CONFLICT (id) DO UPDATE SET {', '.join(updates)};
        """

        params = {
            "id": 1,
            "tg": ADMIN_ID,
            "username": ADMIN_USERNAME,
        }

        conn.execute(text(insert_sql), params)
        s.commit()
        print(f"✅ Admin user ensured successfully in '{table_name}'.")

    except Exception as e:
        print(f"❌ Failed to ensure admin user: {e}")
