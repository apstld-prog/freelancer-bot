from sqlalchemy import create_engine, text
import os

print("======================================================")
print("🧩 DB CLEANUP & SYNC ADMIN TOOL — Final Repair")
print("======================================================")

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("❌ DATABASE_URL not found.")
    exit(1)

engine = create_engine(db_url)

with engine.connect() as conn:

    # --- Step 1: Backup old table (user → user_backup)
    print("📦 Backing up old table 'user' to 'user_backup' (if exists)...")
    conn.execute(text("DROP TABLE IF EXISTS user_backup;"))
    conn.execute(text("CREATE TABLE IF NOT EXISTS user_backup AS TABLE \"user\";"))
    conn.commit()

    # --- Step 2: Ensure admin exists in users
    print("👤 Checking for admin user 5254014824 in 'users' ...")
    exists = conn.execute(text("SELECT id FROM users WHERE id=5254014824;")).fetchone()

    if not exists:
        print("🧩 Admin missing — inserting fresh record...")
        conn.execute(text("""
            INSERT INTO users (id, telegram_id, started_at, is_admin, is_active)
            VALUES (5254014824, 5254014824, NOW() AT TIME ZONE 'UTC', TRUE, TRUE)
            ON CONFLICT (id) DO NOTHING;
        """))
        conn.commit()
    else:
        print("✅ Admin already exists in 'users'.")

    # --- Step 3: Fix telegram_id duplicates (keep only admin)
    print("🧹 Removing duplicate telegram_id entries (keeping admin only)...")
    conn.execute(text("""
        DELETE FROM users
        WHERE telegram_id = 5254014824 AND id <> 5254014824;
    """))
    conn.commit()

    # --- Step 4: Drop old foreign key and relink keywords
    print("🔗 Rebuilding foreign key for 'keyword.user_id' → 'users.id' ...")
    conn.execute(text("ALTER TABLE keyword DROP CONSTRAINT IF EXISTS keyword_user_id_fkey;"))
    conn.execute(text("""
        ALTER TABLE keyword
        ADD CONSTRAINT keyword_user_id_fkey
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE;
    """))
    conn.commit()

    # --- Step 5: Clean orphan keywords
    print("🧹 Deleting orphaned keyword entries...")
    conn.execute(text("""
        DELETE FROM keyword WHERE user_id NOT IN (SELECT id FROM users);
    """))
    conn.commit()

    # --- Step 6: Remove old table 'user'
    print("🗑 Dropping old table 'user' (no longer needed)...")
    conn.execute(text("DROP TABLE IF EXISTS \"user\" CASCADE;"))
    conn.commit()

print("🎉 Cleanup complete — database is now consistent.")
print("👉 Next steps:")
print("   python3 init_keywords.py")
print("   ./diagnostic.sh")
print("======================================================")
