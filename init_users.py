from sqlalchemy import create_engine, text
import os

print("======================================================")
print("👤 INIT USERS TOOL — ensure admin and default users")
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

with engine.connect() as conn:
    # Check which table exists
    res = conn.execute(text("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema='public' AND table_name IN ('user', 'users');
    """)).fetchall()
    tables = [r[0] for r in res]
    if not tables:
        print("❌ No user table found in DB.")
        exit(1)

    print(f"✅ Found user-related tables: {tables}")

    # Prefer plural 'users' if exists
    table = "users" if "users" in tables else "user"
    print(f"📊 Using table: {table}")

    # Check columns
    cols = conn.execute(text(f"""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = '{table}';
    """)).fetchall()
    cols = [c[0] for c in cols]
    print(f"📋 Columns: {cols}")

    # Ensure BIGINT id column
    col_info = conn.execute(text(f"""
        SELECT data_type FROM information_schema.columns
        WHERE table_name='{table}' AND column_name='id';
    """)).scalar()
    print(f"ℹ️ id column type: {col_info}")

    # Insert admin user
    try:
        print(f"🧩 Inserting admin user ({ADMIN_ID})...")
        conn.execute(text(f"""
            INSERT INTO "{table}" (id, telegram_id, started_at, is_admin, is_active)
            VALUES (:id, :tg, NOW() AT TIME ZONE 'UTC', TRUE, TRUE)
            ON CONFLICT (id) DO NOTHING;
        """), {"id": ADMIN_ID, "tg": ADMIN_ID})
        conn.commit()
        print("✅ Admin user ensured successfully.")
    except Exception as e:
        print(f"❌ init_users failed: {e}")
        exit(1)

print("🎉 Done! Now run:")
print("   python3 init_keywords.py")
print("======================================================")
