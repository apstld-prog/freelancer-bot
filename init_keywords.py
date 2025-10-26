import os
from sqlalchemy import create_engine, text

print("======================================================")
print("🔑 INIT KEYWORDS TOOL — ensure default admin keywords")
print("======================================================")

# ✅ Use admin id = 1 (the working admin)
ADMIN_ID = 1
ADMIN_TELEGRAM_ID = 5254014824

DEFAULT_KEYWORDS = [
    "logo",
    "lighting",
    "led",
    "dialux",
    "relux",
    "photometric"
]

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("❌ DATABASE_URL not found in environment variables.")
    exit(1)

engine = create_engine(db_url)

with engine.connect() as conn:
    # Confirm admin presence
    admin = conn.execute(
        text("SELECT id, telegram_id FROM users WHERE id=:id"),
        {"id": ADMIN_ID}
    ).fetchone()

    if not admin:
        print(f"❌ Admin user {ADMIN_ID} not found in 'users' table.")
        exit(1)
    else:
        print(f"✅ Admin user found in 'users': {admin}")

    print("🧩 Seeding default keywords for admin...")

    for kw in DEFAULT_KEYWORDS:
        try:
            conn.execute(
                text("""
                    INSERT INTO keyword (user_id, keyword, value, created_at, updated_at)
                    VALUES (:uid, :kw, :kw, NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC')
                    ON CONFLICT DO NOTHING;
                """),
                {"uid": ADMIN_ID, "kw": kw}
            )
        except Exception as e:
            print(f"⚠️ Failed for keyword '{kw}':", e)

    conn.commit()

print("✅ Default keywords ensured successfully.")
print("======================================================")
