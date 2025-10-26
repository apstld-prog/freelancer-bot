# init_users.py
"""
Ensures that the core user entries (admin and system defaults) exist in the database.
Safe to run multiple times — will not duplicate records.
"""

from db import get_session
from sqlalchemy import text

ADMIN_ID = 5254014824
DEFAULT_USERS = [
    {"id": ADMIN_ID, "username": "admin"},
    {"id": 7916253053, "username": "default_user"},
]

with get_session() as s:
    conn = s.connection()
    try:
        # Βεβαιώσου ότι υπάρχει ο πίνακας "user" ή "users"
        table_name = None
        res = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema='public' AND table_name ILIKE 'user%';
        """)).fetchall()
        if res:
            table_name = res[0][0]
            print(f"✅ Found user table: {table_name}")
        else:
            print("❌ No user table found in database. Cannot continue.")
            exit(1)

        # Δημιούργησε admin + default users αν δεν υπάρχουν
        for u in DEFAULT_USERS:
            conn.execute(text(f"""
                INSERT INTO "{table_name}" (id, username, created_at)
                VALUES (:id, :username, NOW() AT TIME ZONE 'UTC')
                ON CONFLICT (id) DO NOTHING;
            """), {"id": u["id"], "username": u["username"]})
        s.commit()
        print(f"✅ Ensured {len(DEFAULT_USERS)} base users (admin + defaults).")

        # Έλεγξε πόσοι υπάρχουν συνολικά
        count_users = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
        print(f"👥 Total users in DB: {count_users}")

    except Exception as e:
        print(f"❌ init_users failed: {e}")
