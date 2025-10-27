from sqlalchemy import create_engine, text
import os

# --------------------------------------------------
# Load DATABASE_URL from environment
# --------------------------------------------------
db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("❌ DATABASE_URL not found in environment.")
    exit(1)

engine = create_engine(db_url, future=True)

print("======================================================")
print("🧩 FIX TELEGRAM_ID → BIGINT MIGRATION TOOL (user + users)")
print("======================================================")

def fix_table(table_name):
    print(f"🔧 Checking table: {table_name}")
    with engine.begin() as conn:
        info = conn.execute(text(f"""
            SELECT data_type FROM information_schema.columns
            WHERE table_name='{table_name}' AND column_name='telegram_id';
        """)).fetchone()

        if not info:
            print(f"⚠️  Table '{table_name}' not found, skipping.")
            return

        col_type = info[0]
        print(f"ℹ️ Current 'telegram_id' column type: {col_type}")
        if col_type != "bigint":
            print(f"🧩 Altering '{table_name}.telegram_id' from INTEGER to BIGINT...")
            conn.execute(text(f'ALTER TABLE "{table_name}" ALTER COLUMN telegram_id TYPE BIGINT;'))
            print(f"✅ Column type of '{table_name}.telegram_id' changed to BIGINT.")
        else:
            print(f"✅ '{table_name}.telegram_id' is already BIGINT.")

# Run for both possible tables
for tbl in ["users", "user"]:
    fix_table(tbl)

print("======================================================")
print("✅ Migration complete — telegram_id columns are now BIGINT.")
print("======================================================")
print("Now you can safely rerun:")
print("   python3 init_users.py")
print("   python3 init_keywords.py")
