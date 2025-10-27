import os
from sqlalchemy import create_engine, text

print("======================================================")
print("👤 INIT USERS TOOL — ensure admin and default users")
print("======================================================")

ADMIN_ID = 1
ADMIN_TELEGRAM_ID = 5254014824
ADMIN_USERNAME = "admin"

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("❌ DATABASE_URL not found in environment variables.")
    exit(1)

engine = create_engine(db_url, future=True)

with engine.begin() as conn:
    # Detect all user-related tables
    tables = conn.execute(text("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema='public' AND table_name LIKE 'user%';
    """)).fetchall()
    table_names = [t[0] for t in tables]
    print(f"✅ Found user-related tables: {table_names}")

    # Prefer "users" if exists, else fallback to "user"
    target_table = "users" if "users" in table_names else "user"
    print(f"📊 Using table: {target_table}")

    # Detect columns
    cols = conn.execute(text(f"""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='{target_table}';
    """)).fetchall()
    col_names = [c[0] for c in cols]
    print(f"📋 Columns: {col_names}")

    # Build common insert/update logic
    print(f"🧩 Inserting or updating admin user ({ADMIN_ID})...")

    if target_table == "users":
        conn.execute(text("""
            INSERT INTO users (
                id, telegram_id, is_admin, is_active, is_blocked,
                started_at, created_at, updated_at
            )
            VALUES (
                :id, :tg, TRUE, TRUE, FALSE,
                NOW() AT TIME ZONE 'UTC',
                NOW() AT TIME ZONE 'UTC',
                NOW() AT TIME ZONE 'UTC'
            )
            ON CONFLICT (id) DO UPDATE SET
                telegram_id = EXCLUDED.telegram_id,
                is_admin = TRUE,
                is_active = TRUE,
                is_blocked = FALSE,
                updated_at = NOW() AT TIME ZONE 'UTC';
        """), {"id": ADMIN_ID, "tg": ADMIN_TELEGRAM_ID})

    else:
        # If "user" table, handle manually (older schema)
        conn.execute(text("""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM "user" WHERE telegram_id = :tg) THEN
                    UPDATE "user"
                    SET
                        username = :un,
                        is_admin = TRUE,
                        is_active = TRUE,
                        is_blocked = FALSE,
                        updated_at = NOW() AT TIME ZONE 'UTC'
                    WHERE telegram_id = :tg;
                ELSE
                    INSERT INTO "user" (
                        id, telegram_id, username, is_admin, is_active, is_blocked,
                        created_at, updated_at
                    )
                    VALUES (
                        :id, :tg, :un, TRUE, TRUE, FALSE,
                        NOW() AT TIME ZONE 'UTC',
                        NOW() AT TIME ZONE 'UTC'
                    );
                END IF;
            END
            $$;
        """), {"id": ADMIN_ID, "tg": ADMIN_TELEGRAM_ID, "un": ADMIN_USERNAME})

    print("✅ Admin ensured successfully.")

print("======================================================")
print("✅ init_users complete — admin is now synchronized.")
print("======================================================")
