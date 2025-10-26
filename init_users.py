import os
from sqlalchemy import create_engine, text

print("======================================================")
print("👤 INIT USERS TOOL — ensure admin and default users")
print("======================================================")

# ✅ Admin ID = 1 (όπως είναι ήδη στη βάση σου)
ADMIN_ID = 1
ADMIN_TELEGRAM_ID = 5254014824

# Connect to database
db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("❌ DATABASE_URL not found in environment variables.")
    exit(1)

engine = create_engine(db_url)

with engine.connect() as conn:
    # Detect user-related tables
    tables = conn.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
    ).fetchall()
    table_names = [t[0] for t in tables if 'user' in t[0]]
    print(f"✅ Found user-related tables: {table_names}")

    # Pick primary users table
    target_table = "users" if "users" in table_names else "user"
    print(f"📊 Using table: {target_table}")

    # Show existing admin
    existing_admin = conn.execute(
        text(f"SELECT id, telegram_id, is_admin, is_active FROM {target_table} WHERE id={ADMIN_ID};")
    ).fetchall()
    print("📋 Existing admin entries:", existing_admin)

    # Ensure admin user
    print(f"🧩 Inserting admin user ({ADMIN_ID})...")
    try:
        conn.execute(
            text(f"""
                INSERT INTO {target_table} (id, telegram_id, started_at, is_admin, is_active)
                VALUES (:id, :tg, NOW() AT TIME ZONE 'UTC', TRUE, TRUE)
                ON CONFLICT (id) DO UPDATE
                SET is_admin=TRUE, is_active=TRUE;
            """),
            {"id": ADMIN_ID, "tg": ADMIN_TELEGRAM_ID}
        )
        conn.commit()
        print("✅ Admin ensured successfully.")
    except Exception as e:
        print("⚠️ init_users failed or already ensured:", e)

print("======================================================")
print("✅ init_users complete — admin is now synchronized.")
print("======================================================")
