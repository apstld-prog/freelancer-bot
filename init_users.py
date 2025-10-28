import os
from sqlalchemy import create_engine, text

print("======================================================")
print("👤 INIT USERS TOOL — ensure admin and default users")
print("======================================================")

ADMIN_ID = 1
ADMIN_TELEGRAM_ID = 5254014824
ADMIN_USERNAME = "admin"

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

    for tbl in ["user", "users"]:
        if tbl not in table_names:
            print(f"⚠️ Table '{tbl}' not found — skipping.")
            continue

        print(f"📊 Ensuring admin in table: {tbl}")
        try:
            conn.execute(
                text(f"""
                    INSERT INTO {tbl} (id, telegram_id, username, is_admin, is_active, created_at)
                    VALUES (:id, :tg, :username, TRUE, TRUE, NOW() AT TIME ZONE 'UTC')
                    ON CONFLICT (id) DO UPDATE
                    SET telegram_id = EXCLUDED.telegram_id,
                        username = EXCLUDED.username,
                        is_admin = TRUE,
                        is_active = TRUE;
                """),
                {"id": ADMIN_ID, "tg": ADMIN_TELEGRAM_ID, "username": ADMIN_USERNAME}
            )
            conn.commit()
            print(f"✅ Admin ensured in '{tbl}'.")
        except Exception as e:
            print(f"⚠️ Failed to ensure admin in '{tbl}':", e)

print("======================================================")
print("✅ init_users complete — admin synchronized in all tables.")
print("======================================================")
