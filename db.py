import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")


class PsycopgSession:
    """Wrapper για psycopg2 connection με context manager."""
    def __init__(self):
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL not set")
        self.conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        self.cur = self.conn.cursor()

    def execute(self, query: str, params=None):
        self.cur.execute(query, params or ())
        return self.cur

    def fetchone(self):
        return self.cur.fetchone()

    def fetchall(self):
        return self.cur.fetchall()

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        try:
            self.cur.close()
        finally:
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()


def get_session() -> PsycopgSession:
    return PsycopgSession()


def ensure_schema():
    """Δημιουργεί ή ενημερώνει το βασικό schema της βάσης."""
    with get_session() as s:
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

        s.execute("""
        CREATE TABLE IF NOT EXISTS saved_job (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            title TEXT NOT NULL,
            url TEXT,
            description TEXT,
            saved_at TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'UTC')
        );
        """)

        # trigger για updated_at
        s.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_proc WHERE proname = 'set_updated_at_user'
            ) THEN
                CREATE OR REPLACE FUNCTION set_updated_at_user()
                RETURNS TRIGGER AS $f$
                BEGIN
                    NEW.updated_at = (NOW() AT TIME ZONE 'UTC');
                    RETURN NEW;
                END;
                $f$ LANGUAGE plpgsql;
            END IF;
        END$$;
        """)

        s.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname = 'trg_user_updated_at'
            ) THEN
                CREATE TRIGGER trg_user_updated_at
                BEFORE UPDATE ON "user"
                FOR EACH ROW
                EXECUTE FUNCTION set_updated_at_user();
            END IF;
        END$$;
        """)


def get_or_create_user_by_tid(telegram_id: int, username: str = None):
    """
    Επιστρέφει υπάρχοντα χρήστη ή δημιουργεί νέο (αν δεν υπάρχει).
    Επιστρέφει dict με όλα τα πεδία.
    """
    with get_session() as s:
        s.execute('SELECT * FROM "user" WHERE telegram_id=%s;', (telegram_id,))
        row = s.fetchone()

        if row:
            # ενημέρωσε το username αν έχει αλλάξει
            if username and username != row.get("username"):
                s.execute('UPDATE "user" SET username=%s WHERE telegram_id=%s;', (username, telegram_id))
                s.commit()
            return row

        # διαφορετικά, δημιουργεί νέο
        s.execute(
            'INSERT INTO "user" (telegram_id, username, is_active) VALUES (%s, %s, TRUE) RETURNING *;',
            (telegram_id, username)
        )
        user = s.fetchone()
        s.commit()
        return user
