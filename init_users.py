# init_users.py
"""
Ensures that the admin and default users exist in the current database schema.
This version auto-detects column names and adapts to 'users' or 'user' table.
"""

from db import get_session
from sqlalchemy import text

ADMIN_ID = 5254014824  # Telegram ID of the admin
DEFAULT_USERS = [
    {"id": ADMIN_ID, "telegram_id": ADMIN_ID},
]

with get_session() as s:
    conn = s.connection()
    try:
        # Εντοπίζει τον σωστό πίνακα (user ή users)
        res = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema='public' AND table_name ILIKE 'user%';
        """)).fetchall()

        if not res:
            print("❌ No user table found in database.")
            exit(1)

        table_name = res[0][0]
        print(f"✅ Found user table: {table_name}")

        # Παίρνει λίστα στηλών του πίνακα
        cols = [r[0] for r in conn.execute(text(f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_name=:tname;
        """), {"tname": table_name}).fetchall()]

        print(f"📊 Columns in table '{table_name}': {cols}")

        # Δημιουργεί admin με τα διαθέσιμα πεδία
        for u in DEFAULT_USERS:
            if "telegram_id" in cols:
                conn.execute(text(f"""
                    INSERT INTO "{table_name}" (id, telegram_id, started_at)
                    VALUES (:id, :telegram_id, NOW() AT TIME ZONE 'UTC')
                    ON CONFLICT (id) DO NOTHING;
                """), {"id": u["id"], "telegram_id": u["telegram_id"]})
            else:
                conn.execute(text(f"""
                    INSERT INTO "{table_name}" (id, started_at)
                    VALUES (:id, NOW() AT TIME ZONE 'UTC')
                    ON CONFLICT (id) DO NOTHING;
                """), {"id": u["id"]})
        s.commit()

        print("✅ Admin user ensured successfully.")
        count_users = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
        print(f"👥 Total users in DB: {count_users}")

    except Exception as e:
        print(f"❌ init_users failed: {e}")
