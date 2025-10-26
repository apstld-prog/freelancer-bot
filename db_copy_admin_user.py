from sqlalchemy import create_engine, text
import os

print("======================================================")
print("👤 DB TOOL — Copy admin from `user` → `users`")
print("======================================================")

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("❌ DATABASE_URL not found.")
    exit(1)

engine = create_engine(db_url)

with engine.connect() as conn:
    # Check both tables exist
    tables = conn.execute(text("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema='public';
    """)).fetchall()
    tables = [t[0] for t in tables]
    if "user" not in tables or "users" not in tables:
        print("❌ Missing required tables: 'user' or 'users'")
        exit(1)

    # Check if admin exists in users
    existing = conn.execute(text("SELECT id FROM users WHERE id=5254014824;")).fetchone()
    if existing:
        print("✅ Admin already exists in `users`.")
    else:
        print("🧩 Copying admin from `user` → `users` ...")
        conn.execute(text("""
            INSERT INTO users (id, telegram_id, started_at, is_admin, is_active)
            SELECT u.id, u.telegram_id, NOW() AT TIME ZONE 'UTC', TRUE, TRUE
            FROM "user" AS u
            WHERE u.id = 5254014824
            ON CONFLICT (id) DO NOTHING;
        """))
        conn.commit()
        print("✅ Admin successfully copied into `users`.")

print("🎉 Done! Now run:")
print("   python3 init_keywords.py")
print("======================================================")
