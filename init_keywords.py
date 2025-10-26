# init_keywords.py
# Ensures default keywords exist for the admin user (and fixes missing session import)

import os, sys
from sqlalchemy import text

sys.path.append(os.path.dirname(__file__))
from db import get_session  # ✅ changed from "session" to "get_session"

DEFAULT_KEYWORDS = [
    "logo",
    "lighting",
    "dialux",
    "relux",
    "led",
    "φωτισμός",
    "luminaire",
]

ADMIN_ID = 5254014824  # your Telegram admin user ID

def ensure_keywords():
    """Ensure default keywords exist for the admin user."""
    with get_session() as s:
        conn = s.connection()

        # ✅ 1. Ensure admin user exists (if not, create)
        try:
            conn.execute(text("""
                INSERT INTO "user" (id, username, role, created_at)
                VALUES (:id, 'admin', 'admin', NOW() AT TIME ZONE 'UTC')
                ON CONFLICT (id) DO NOTHING;
            """), {"id": ADMIN_ID})
            s.commit()
            print(f"✅ Admin user ensured in 'user' table.")
        except Exception as e:
            print(f"⚠️ Warning: Could not ensure admin user: {e}")

        # ✅ 2. Fetch existing keywords
        try:
            rows = conn.execute(text("SELECT keyword FROM keyword WHERE user_id = :uid"), {"uid": ADMIN_ID}).fetchall()
            existing = [r[0] for r in rows]
        except Exception as e:
            print(f"⚠️ Warning: Could not fetch existing keywords ({e})")
            existing = []

        # ✅ 3. Find missing ones
        missing = [k for k in DEFAULT_KEYWORDS if k not in existing]

        # ✅ 4. Insert new keywords if needed
        if missing:
            print(f"🔄 Inserting missing keywords for admin: {missing}")
            for kw in missing:
                try:
                    conn.execute(text("""
                        INSERT INTO keyword (user_id, keyword, value, created_at, updated_at)
                        VALUES (:uid, :kw, :kw, NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC')
                        ON CONFLICT DO NOTHING;
                    """), {"uid": ADMIN_ID, "kw": kw})
                except Exception as e:
                    print(f"❌ Failed to insert keyword '{kw}': {e}")
            s.commit()
            print("✅ Default keywords inserted successfully.")
        else:
            print("✅ All default keywords already exist for admin.")


if __name__ == "__main__":
    ensure_keywords()
