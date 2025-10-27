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

    # Prefer table 'user' if exists (it’s the complete one)
    if "user" in table_names:
        target_table = "user"
    elif "users" in table_names:
        target_table = "users"
    else:
        print("❌ No suitable user table found. Exiting.")
        exit(1)

    print(f"📊 Using table: {target_table}")

    # Detect available columns
    cols = conn.execute(text(f"""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='{target_table}';
    """)).fetchall()
    col_names = [c[0] for c in cols]
    print(f"📋 Columns in table '{target_table}': {col_names}")

    # Base insert
    sql_cols = ["id", "telegram_id", "is_admin", "is_active", "is_blocked", "created_at", "updated_at"]
    sql_vals = [":id", ":tg", "TRUE", "TRUE", "FALSE", "NOW() AT TIME ZONE 'UTC'", "NOW() AT TIME ZONE 'UTC'"]

    # Add username column only if it exists
    if "username" in col_names:
        sql_cols.insert(2, "username")
        sql_vals.insert(2, ":un")

    sql = f"""
        INSERT INTO "{target_table}" ({', '.join(sql_cols)})
        VALUES ({', '.join(sql_vals)})
        ON CONFLICT (telegram_id) DO UPDATE
        SET is_admin = TRUE,
            is_active = TRUE,
            is_blocked = FALSE,
            updated_at = NOW() AT TIME ZONE 'UTC'
    """

    if "username" in col_names:
        sql += ", username = EXCLUDED.username"

    sql += ";"

    print(f"🧩 Ensuring admin user (id={ADMIN_ID}, telegram_id={ADMIN_TELEGRAM_ID})...")

    conn.execute(
        text(sql),
        {"id": ADMIN_ID, "tg": ADMIN_TELEGRAM_ID, "un": ADMIN_USERNAME},
    )

    print("✅ Admin ensured successfully.")

print("======================================================")
print("✅ init_users complete — admin is now synchronized.")
print("======================================================")
