# init_keywords.py
from db import get_session
from sqlalchemy import text

DEFAULT_KEYWORDS = [
    "logo", "lighting", "dialux", "relux", "led", "φωτισμός", "luminaire"
]
ADMIN_ID = 5254014824  # ίδιο με το bot admin ID

with get_session() as s:
    conn = s.connection()
    try:
        # Βεβαιώσου ότι υπάρχει admin στον πίνακα user ή users
        user_exists = conn.execute(text("""
            SELECT id FROM "user" WHERE id = :uid
        """), {"uid": ADMIN_ID}).fetchone()

        if not user_exists:
            # Αν δεν υπάρχει πίνακας 'user', ψάχνει για 'users'
            alt_table = conn.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema='public' AND table_name ILIKE 'user%';
            """)).fetchone()
            if alt_table:
                table = alt_table[0]
                user_exists = conn.execute(text(f"""
                    SELECT id FROM "{table}" WHERE id = :uid
                """), {"uid": ADMIN_ID}).fetchone()
            else:
                print("❌ No user table found, cannot seed keywords.")
                exit(1)

        if not user_exists:
            print("⚠️ Admin user not found, skipping keyword seeding.")
            exit(0)

        print("✅ Admin user found, seeding default keywords...")

        for kw in DEFAULT_KEYWORDS:
            conn.execute(text("""
                INSERT INTO keyword (user_id, keyword, value, created_at, updated_at)
                VALUES (:uid, :kw, :kw, NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC')
                ON CONFLICT DO NOTHING;
            """), {"uid": ADMIN_ID, "kw": kw})

        s.commit()
        print(f"✅ Seeded {len(DEFAULT_KEYWORDS)} default keywords for admin ({ADMIN_ID}).")

    except Exception as e:
        print(f"❌ Keyword seeding failed: {e}")
