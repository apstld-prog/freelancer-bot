from sqlalchemy import create_engine, text
import os

print("======================================================")
print("🧩 DB AUTO FIX — Full admin & keyword repair")
print("======================================================")

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("❌ DATABASE_URL not found.")
    exit(1)

engine = create_engine(db_url)

with engine.connect() as conn:

    # 1️⃣ Ensure users.id is BIGINT
    print("🔧 Ensuring users.id is BIGINT...")
    conn.execute(text("ALTER TABLE users ALTER COLUMN id TYPE BIGINT;"))
    conn.commit()

    # 2️⃣ Ensure keyword.user_id is BIGINT
    print("🔧 Ensuring keyword.user_id is BIGINT...")
    conn.execute(text("ALTER TABLE keyword ALTER COLUMN user_id TYPE BIGINT;"))
    conn.commit()

    # 3️⃣ Ensure correct FK link
    print("🔗 Relinking keyword.user_id → users.id ...")
    conn.execute(text("ALTER TABLE keyword DROP CONSTRAINT IF EXISTS keyword_user_id_fkey;"))
    conn.execute(text("""
        ALTER TABLE keyword
        ADD CONSTRAINT keyword_user_id_fkey
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE;
    """))
    conn.commit()

    # 4️⃣ Copy admin record if missing
    print("👤 Checking for admin in users table...")
    res = conn.execute(text("SELECT id FROM users WHERE id=5254014824;")).fetchone()
    if not res:
        print("🧩 Copying admin from user → users ...")
        conn.execute(text("""
            INSERT INTO users (id, telegram_id, started_at, is_admin, is_active)
            SELECT id, telegram_id, NOW() AT TIME ZONE 'UTC', TRUE, TRUE
            FROM user
            WHERE id=5254014824
            ON CONFLICT (id) DO NOTHING;
        """))
        conn.commit()
        print("✅ Admin copied successfully.")
    else:
        print("✅ Admin already exists in users.")

    # 5️⃣ Clean any orphan keywords
    print("🧹 Cleaning orphan keyword records...")
    conn.execute(text("""
        DELETE FROM keyword WHERE user_id NOT IN (SELECT id FROM users);
    """))
    conn.commit()

print("🎉 All fixes complete.")
print("Now run:")
print("   python3 init_keywords.py")
print("======================================================")
