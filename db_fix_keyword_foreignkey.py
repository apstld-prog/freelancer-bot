from sqlalchemy import create_engine, text
import os

print("======================================================")
print("🧩 DB PATCH — fix keyword.user_id foreign key target")
print("======================================================")

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("❌ DATABASE_URL not found.")
    exit(1)

engine = create_engine(db_url)

with engine.connect() as conn:
    # Check if keyword table exists
    res = conn.execute(text("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema='public' AND table_name='keyword';
    """)).fetchone()
    if not res:
        print("❌ Table 'keyword' not found.")
        exit(1)

    # Drop the old FK
    print("🔧 Dropping old foreign key constraint (if exists)...")
    try:
        conn.execute(text("ALTER TABLE keyword DROP CONSTRAINT IF EXISTS keyword_user_id_fkey;"))
    except Exception as e:
        print("⚠️ Could not drop constraint:", e)

    # Recreate the FK to point to 'users'
    print("🧩 Creating new foreign key to 'users(id)'...")
    conn.execute(text("""
        ALTER TABLE keyword
        ADD CONSTRAINT keyword_user_id_fkey
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE;
    """))
    conn.commit()

print("✅ Foreign key now points to 'users.id'")
print("🎉 Done! You can now safely rerun:")
print("   python3 init_keywords.py")
print("======================================================")
