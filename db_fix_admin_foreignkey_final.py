from sqlalchemy import create_engine, text
import os

print("======================================================")
print("🧩 DB FIX — Final Admin & Foreign Key Repair")
print("======================================================")

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("❌ DATABASE_URL not found.")
    exit(1)

engine = create_engine(db_url)

with engine.connect() as conn:
    # Step 1: show users table summary
    print("📊 Checking current admin entries...")
    users = conn.execute(text("""
        SELECT id, telegram_id, is_admin, is_active
        FROM users
        WHERE telegram_id=5254014824;
    """)).fetchall()
    print("Found:", users)

    # Step 2: fix keywords linked to wrong id (1)
    print("🧩 Relinking keywords to proper user id=5254014824...")
    conn.execute(text("""
        UPDATE keyword
        SET user_id = 5254014824
        WHERE user_id IN (SELECT id FROM users WHERE telegram_id=5254014824)
           OR user_id = 1;
    """))
    conn.commit()

    # Step 3: drop old admin if exists (id=1) safely
    print("🗑 Removing outdated admin id=1 (keeping keywords relinked)...")
    conn.execute(text("""
        DELETE FROM keyword WHERE user_id NOT IN (SELECT id FROM users);
    """))
    conn.commit()

    try:
        conn.execute(text("DELETE FROM users WHERE id=1;"))
        conn.commit()
    except Exception as e:
        print("⚠️ Could not delete id=1 (already gone):", e)

    # Step 4: ensure correct admin user
    print("👤 Ensuring admin 5254014824 exists...")
    conn.execute(text("""
        INSERT INTO users (id, telegram_id, started_at, is_admin, is_active)
        VALUES (5254014824, 5254014824, NOW() AT TIME ZONE 'UTC', TRUE, TRUE)
        ON CONFLICT (id) DO UPDATE
        SET is_admin=TRUE, is_active=TRUE;
    """))
    conn.commit()

    # Step 5: rebuild FK constraint
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

    # Step 6: verify
    print("🔍 Verifying...")
    admin = conn.execute(text("""
        SELECT id, telegram_id, is_admin, is_active FROM users WHERE id=5254014824;
    """)).fetchone()
    print("✅ Admin record:", admin)
    keyword_count = conn.execute(text("SELECT COUNT(*) FROM keyword;")).scalar()
    print("✅ Keywords in DB:", keyword_count)

print("🎉 FIX COMPLETE — DB now consistent.")
print("👉 Next:")
print("   python3 init_keywords.py")
print("   ./diagnostic.sh")
print("======================================================")
