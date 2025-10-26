from sqlalchemy import create_engine, text
import os

print("======================================================")
print("🧩 DB PATCH — ensure admin-related columns in 'users'")
print("======================================================")

# --------------------------------------------------
# Load DATABASE_URL
# --------------------------------------------------
db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("❌ DATABASE_URL not found in environment.")
    exit(1)

engine = create_engine(db_url)

with engine.connect() as conn:
    # Check if 'users' exists
    res = conn.execute(text("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema='public' AND table_name='users';
    """)).fetchone()

    if not res:
        print("❌ Table 'users' not found.")
        exit(1)

    # Check columns
    cols = [r[0] for r in conn.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='users';
    """)).fetchall()]
    print(f"📋 Existing columns: {cols}")

    # Add missing columns
    added = []
    if "is_admin" not in cols:
        conn.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE;"))
        added.append("is_admin")
    if "is_active" not in cols:
        conn.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT TRUE;"))
        added.append("is_active")

    if added:
        conn.commit()
        print(f"✅ Added columns: {added}")
    else:
        print("✅ All necessary columns already exist.")

print("🎉 Done! You can now rerun:")
print("   python3 init_users.py")
print("======================================================")
