import os
from sqlalchemy import create_engine, text

print("======================================================")
print("👤 INIT USERS TOOL — ensure admin and default users")
print("======================================================")

ADMIN_ID = 1
ADMIN_TELEGRAM_ID = 5254014824

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

    # Pick main user table
    target_table = "users" if "users" in table_names else "user"
    print(f"📊 Using table: {target_table}")

    # Detect if table has username column
    cols = conn.execute(text(f"""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='{target_table}';
    """)).fetchall()
    col_names = [c[0] for c in cols]

    has_username = "username" in col_names
    has_telegram = "telegram_id" in col_names

    print(f"📋 Columns: {col_names}")

    # Show existing admin
    existing = conn.execute(text(f"""
        SELECT id, telegram_id, is_admin, is_active
        FROM "{target_table}"
        WHERE telegram_id = :tg;
    """), {"tg": ADMIN_TELEGRAM_ID}).fetchall()
    print(f"📋 Existing admin entries: {existing}")

    # Build INSERT dynamically based on table schema
    print(f"🧩 Inserting admin user ({ADMIN_ID})...")

    if has_username and has_telegram:
        conn.execute(text(f"""
            INSERT INTO "{target_table}" (id, telegram_id, username, is_admin, is_active, started_at)
            VALUES (:id, :tg, 'admin', TRUE, TRUE, NOW() AT TIME ZONE 'UTC')
            ON CONFLICT (id) DO UPDATE
            SET telegram_id = :tg, is_admin = TRUE, is_active = TRUE;
        """), {"id": ADMIN_ID, "tg": ADMIN_TELEGRAM_ID})

    elif has_telegram and not has_username:
        conn.execute(text(f"""
            INSERT INTO "{target_table}" (id, telegram_id, is_admin, is_active, started_at)
            VALUES (:id, :tg, TRUE, TRUE, NOW() AT TIME ZONE 'UTC')
            ON CONFLICT (id) DO UPDATE
            SET telegram_id = :tg, is_admin = TRUE, is_active = TRUE;
        """), {"id": ADMIN_ID, "tg": ADMIN_TELEGRAM_ID})

    elif not has_telegram and has_username:
        conn.execute(text(f"""
            INSERT INTO "{target_table}" (id, username, is_admin, is_active, started_at)
            VALUES (:id, 'admin', TRUE, TRUE, NOW() AT TIME ZONE 'UTC')
            ON CONFLICT (id) DO UPDATE
            SET is_admin = TRUE, is_active = TRUE;
        """), {"id": ADMIN_ID})

    else:
        conn.execute(text(f"""
            INSERT INTO "{target_table}" (id, is_admin, is_active, started_at)
            VALUES (:id, TRUE, TRUE, NOW() AT TIME ZONE 'UTC')
            ON CONFLICT (id) DO NOTHING;
        """), {"id": ADMIN_ID})

    print("✅ Admin ensured successfully.")

print("======================================================")
print("✅ init_users complete — admin is now synchronized.")
print("======================================================")
