from sqlalchemy import create_engine, text
import os

print("======================================================")
print("🧩 DB PATCH — relink keyword.user_id → users.id")
print("======================================================")

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("❌ DATABASE_URL not found.")
    exit(1)

engine = create_engine(db_url)

with engine.connect() as conn:
    # Drop existing FK to "user"
    print("🔧 Dropping existing foreign key constraint (if any)...")
    conn.execute(text("""
        ALTER TABLE keyword
        DROP CONSTRAINT IF EXISTS keyword_user_id_fkey;
    """))
    conn.commit()

    # Ensure all old orphan user_ids are removed
    print("🧹 Cleaning orphan keyword records (user_id not in users)...")
    conn.execute(text("""
        DELETE FROM keyword
        WHERE user_id NOT IN (SELECT id FROM users);
    """))
    conn.commit()

    # Add correct FK
    print("🧩 Linking keyword.user_id → users.id ...")
    conn.execute(text("""
        ALTER TABLE keyword
        ADD CONSTRAINT keyword_user_id_fkey
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE;
    """))
    conn.commit()

print("✅ Foreign key fixed — now points to 'users.id'")
print("🎉 Done! You can now rerun:")
print("   python3 init_keywords.py")
print("======================================================")
