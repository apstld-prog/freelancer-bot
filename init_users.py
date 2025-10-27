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

    # Determine main table
    target_table = "users" if "users" in table_names else "user"
    print(f"📊 Using table: {target_table}")

    # Detect columns
    cols = conn.execute(text(f"""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='{target_table}';
    """)).fetchall()
    col_names = [c[0] for c in cols]
    print(f"📋 Columns: {col_names}")

    has_username = "username" in col_names
    has_telegram = "telegram_id" in col_names
    has_is_admin = "is_admin" in col_names
    has_is_active = "is_active" in col_names
    has_started = "started_at" in col_names

    # Show existing admin entries
    existing = conn.execute(text(f"""
        SELECT id, telegram_id, is_admin, is_active
        FROM "{target_table}"
        WHERE telegram_id = :tg;
    """), {"tg": ADMIN_TELEGRAM_ID}).fetchall()
    print(f"📋 Existing admin entries: {existing}")

    print(f"🧩 Inserting or updating admin user ({ADMIN_ID})...")

    # Build dynamic insert ensuring telegram_id always present
    base_insert = f'INSERT INTO "{target_table}" (id'
    base_values = "VALUES (:id"
    update_clause = "ON CONFLICT (id) DO UPDATE SET "

    params = {"id": ADMIN_ID, "tg": ADMIN_TELEGRAM_ID, "un": ADMIN_USERNAME}

    # Always include telegram_id if exists
    if has_telegram:
        base_insert += ", telegram_id"
        base_values += ", :tg"
        update_clause += "telegram_id=:tg, "

    # Include username if available
    if has_username:
        base_insert += ", username"
        base_values += ", :un"

    # Always mark as admin + active
    if has_is_admin:
        base_insert += ", is_admin"
        base_values += ", TRUE"
        update_clause += "is_admin=TRUE, "
    if has_is_active:
        base_insert += ", is_active"
        base_values += ", TRUE"
        update_clause += "is_active=TRUE, "

    # Add started_at if column exists
    if has_started:
        base_insert += ", started_at"
        base_values += ", NOW() AT TIME ZONE 'UTC'"

    # Close the insert
    base_insert += ") "
    base_values += ") "
    sql = base_insert + base_values + update_clause.rstrip(", ") + ";"

    conn.execute(text(sql), params)
    print("✅ Admin ensured successfully.")

print("======================================================")
print("✅ init_users complete — admin is now synchronized.")
print("======================================================")
