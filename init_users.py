import os
from db import get_session

ADMIN_TID_DEFAULT = "5254014824"  # δικό σου admin chat id ως default

def ensure_admin_user():
    admin_tid = os.getenv("ADMIN_TELEGRAM_ID", ADMIN_TID_DEFAULT)

    with get_session() as s:
        # Βεβαιώσου ότι υπάρχει ο πίνακας "user"
        s.execute("""
        CREATE TABLE IF NOT EXISTS "user" (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE,
            username TEXT,
            is_admin BOOLEAN DEFAULT FALSE NOT NULL,
            is_active BOOLEAN DEFAULT TRUE NOT NULL,
            is_blocked BOOLEAN DEFAULT FALSE NOT NULL,
            trial_start TIMESTAMP,
            trial_end TIMESTAMP,
            license_until TIMESTAMP,
            trial_reminder_sent BOOLEAN,
            created_at TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'UTC'),
            updated_at TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'UTC') NOT NULL,
            started_at TIMESTAMP,
            countries TEXT,
            proposal_template TEXT,
            name TEXT,
            keywords TEXT
        );
        """)

        # Αν υπάρχει εγγραφή id=1, ενεργοποίησέ την ως admin
        s.execute('SELECT id FROM "user" WHERE id=1;')
        row = s.fetchone()
        if row is None:
            s.execute(
                'INSERT INTO "user" (id, telegram_id, username, is_admin, is_active) VALUES (1, %s, %s, TRUE, TRUE);',
                (admin_tid, "admin")
            )
            print("✅ Created admin (id=1).")
        else:
            s.execute('UPDATE "user" SET is_admin=TRUE, is_active=TRUE WHERE id=1;')
            print("✅ Admin id=1 ensured (active).")

        # Σιγουρέψου ότι υπάρχει και εγγραφή με το συγκεκριμένο telegram_id (αν διαφέρει)
        s.execute('SELECT id FROM "user" WHERE telegram_id=%s;', (admin_tid,))
        r2 = s.fetchone()
        if r2 is None:
            s.execute(
                'INSERT INTO "user" (telegram_id, username, is_admin, is_active) VALUES (%s, %s, TRUE, TRUE);',
                (admin_tid, "admin")
            )
            print("✅ Created admin by telegram_id.")
        else:
            s.execute('UPDATE "user" SET is_admin=TRUE, is_active=TRUE WHERE telegram_id=%s;', (admin_tid,))
            print("✅ Admin by telegram_id ensured (active).")


if __name__ == "__main__":
    print("====================================================")
    print("🔧 AUTO-FIX: ADMIN USER IN POSTGRES DATABASE")
    print("====================================================")
    ensure_admin_user()
    print("====================================================")
    print("✅ ADMIN USER FIX COMPLETED SUCCESSFULLY")
    print("====================================================")
