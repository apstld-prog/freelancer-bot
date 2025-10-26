from sqlalchemy import create_engine, text
import os

print("======================================================")
print("🧩 DB PATCH — ensure keyword.user_id is BIGINT")
print("======================================================")

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("❌ DATABASE_URL not found in environment.")
    exit(1)

engine = create_engine(db_url)

with engine.connect() as conn:
    # Check if table exists
    res = conn.execute(text("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema='public' AND table_name='keyword';
    """)).fetchone()

    if not res:
        print("❌ Table 'keyword' not found.")
        exit(1)

    # Get column type
    col_type = conn.execute(text("""
        SELECT data_type FROM information_schema.columns
        WHERE table_name='keyword' AND column_name='user_id';
    """)).scalar()

    print(f"ℹ️ Current user_id column type: {col_type}")

    if col_type != "bigint":
        print("🧩 Altering 'keyword.user_id' from INTEGER to BIGINT...")
        conn.execute(text("ALTER TABLE keyword ALTER COLUMN user_id TYPE BIGINT;"))
        conn.commit()
        print("✅ Column type changed to BIGINT.")
    else:
        print("✅ Column already BIGINT, no change needed.")

print("🎉 Migration complete. You can now rerun:")
print("   python3 init_keywords.py")
print("======================================================")
