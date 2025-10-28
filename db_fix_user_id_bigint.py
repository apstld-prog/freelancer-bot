from sqlalchemy import create_engine, text
import os

# --------------------------------------------------
# Load DATABASE_URL from environment
# --------------------------------------------------
db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("❌ DATABASE_URL not found in environment.")
    exit(1)

engine = create_engine(db_url)

print("🔧 Checking 'users' table structure...")
with engine.connect() as conn:
    # Check current type of id column
    col_info = conn.execute(text("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'id';
    """)).fetchone()

    if not col_info:
        print("❌ 'users' table or id column not found.")
        exit(1)

    print(f"ℹ️ Current type of id column: {col_info.data_type}")

    if col_info.data_type != "bigint":
        print("🧩 Altering 'users.id' from INTEGER to BIGINT...")
        conn.execute(text("ALTER TABLE users ALTER COLUMN id TYPE BIGINT;"))
        conn.commit()
        print("✅ Column type changed to BIGINT.")
    else:
        print("✅ Already BIGINT — no change needed.")

print("🎉 Migration complete. You can now rerun:")
print("   python3 init_users.py")
