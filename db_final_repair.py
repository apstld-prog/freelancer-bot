from sqlalchemy import create_engine, text
import os

print("======================================================")
print("🧩 DB FINAL REPAIR — Full sync & cleanup of users/admin/keywords")
print("======================================================")

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("❌ DATABASE_URL not found.")
    exit(1)

engine = create_engine(db_url)

with engine.connect() as conn:

    # 1️⃣ Backup old table
    print("📦 Backing up old 'user' table to 'user_backup'...")
    conn.execute(text("DROP TABLE IF EXISTS user_backup;"))
    conn.execute(text("CREATE TABLE IF NOT EXISTS user_backup AS TABLE \"user\";"))
    conn.commit()

    # 2️⃣ Remove bad duplicates from 'users'
    print("🧹 Removing duplicate telegram_id=5254014824 entries (keep one)...")
    conn.execute(text("""
        DELETE FROM users
        WHERE telegram_id = 5254014824
        AND id <> 5254014824;
    """))
    conn.commit()

    # 3️⃣ Ensure admin in users
    print("👤 Ensuring admin user (5254014824) exists in 'users'...")
    res = conn.execute(text("SELECT id FROM users WHERE id=5254014824;")).fetchone()
    if not res:
        conn.execute(text("""
            INSERT INTO users (id, telegram_id, started_at, is_admin, is_active)
            VALUES (5254014824, 5254014824, NOW() AT TIME ZONE 'UTC', TRUE, TRUE)
            ON CONFLICT (id) DO NOTHING;
        """))
        conn.commit()
        print("✅ Admin inserted.")
    else:
        print("✅ Admin already exists.")

    # 4️⃣ Drop and rebuild foreign key link
    print("🔗 Rebuilding keyword.user_id foreign key...")
    conn.execute(text("ALTER TABLE keyword DROP CONSTRAINT IF EXISTS keyword_user_id_fkey;"))
    conn.execute(text("""
        ALTER TABLE keyword
        ADD CONSTRAINT keyword_user_id_fkey
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE;
    """))
    conn.commit()

    # 5️⃣ Clean orphan keywords
    print("🧹 Cleaning orphan keyword rows (no matching users)...")
    conn.execute(text("""
        DELETE FROM keyword WHERE user_id NOT IN (SELECT id FROM users);
    """))
    conn.commit()

    # 6️⃣ Remove old 'user' table
    print("🗑 Dropping old 'user' table completely (kept as backup)...")
    conn.execute(text("DROP TABLE IF EXISTS \"user\" CASCADE;"))
    conn.commit()

    # 7️⃣ Verify admin consistency
    print("🔍 Verifying admin in users...")
    check = conn.execute(text("""
        SELECT id, telegram_id, is_admin, is_active FROM users WHERE id=5254014824;
    """)).fetchone()
    print(f"✅ Admin record: {check}")

print("🎉 FINAL REPAIR COMPLETE.")
print("👉 Now run:")
print("   python3 init_keywords.py")
print("   ./diagnostic.sh")
print("======================================================")
