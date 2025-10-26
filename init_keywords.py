from sqlalchemy import create_engine, text
import os

print("======================================================")
print("🔑 INIT KEYWORDS TOOL — ensure default admin keywords")
print("======================================================")

# --------------------------------------------------
# Load DATABASE_URL
# --------------------------------------------------
db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("❌ DATABASE_URL not found in environment.")
    exit(1)

engine = create_engine(db_url)

ADMIN_ID = 5254014824
DEFAULT_KEYWORDS = [
    "logo", "lighting", "dialux", "relux", "led", "φωτισμός", "luminaire"
]

with engine.connect() as conn:
    # Check for 'users' table
    res = conn.execute(text("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema='public' AND table_name IN ('user', 'users');
    """)).fetchall()
    tables = [r[0] for r in res]
    if not tables:
        print("❌ No user table found.")
        exit(1)

    user_table = "users" if "users" in tables else "user"

    # Check if admin exists
    admin = conn.execute(text(f"""
        SELECT id, telegram_id FROM "{user_table}"
        WHERE telegram_id = :tid AND is_admin = TRUE;
    """), {"tid": ADMIN_ID}).fetchone()

    if not admin:
        print("⚠️ Admin user not found in table:", user_table)
        exit(0)

    print(f"✅ Admin user found in '{user_table}': {admin}")

    # Check keyword table
    res = conn.execute(text("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema='public' AND table_name='keyword';
    """)).fetchone()

    if not res:
        print("❌ No 'keyword' table found.")
        exit(1)

    # Seed defaults
    print("🧩 Seeding default keywords for admin...")
    for kw in DEFAULT_KEYWORDS:
        conn.execute(text("""
            INSERT INTO keyword (user_id, keyword, value, created_at, updated_at)
            VALUES (:uid, :kw, :kw, NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC')
            ON CONFLICT DO NOTHING;
        """), {"uid": ADMIN_ID, "kw": kw})
    conn.commit()
    print(f"✅ Inserted defaults for user {ADMIN_ID}: {', '.join(DEFAULT_KEYWORDS)}")

print("🎉 Keyword initialization complete.")
print("======================================================")
