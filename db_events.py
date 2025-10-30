# db_events.py
# Psycopg2-only schema/bootstrap for feed events used by workers/bot

from db import get_session


def ensure_feed_events_schema() -> None:
    with get_session() as s:
        # feed_event: unified stash of fetched jobs
        s.execute("""
        CREATE TABLE IF NOT EXISTS feed_event (
            id BIGSERIAL PRIMARY KEY,
            platform TEXT NOT NULL,            -- 'Freelancer', 'PeoplePerHour', 'Skywalker', etc.
            title TEXT,
            description TEXT,
            affiliate_url TEXT,
            original_url  TEXT,
            budget_amount NUMERIC(18,2) NULL,
            budget_currency TEXT NULL,
            budget_usd NUMERIC(18,2) NULL,
            created_at TIMESTAMPTZ NULL,       -- remote job "posted at" if present
            fetched_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC') NOT NULL,
            dedup_key TEXT NULL
        );
        """)
        s.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname='ux_feed_event_dedup_key'
            ) THEN
                CREATE UNIQUE INDEX ux_feed_event_dedup_key ON feed_event(dedup_key);
            END IF;
        END$$;
        """)

        # Optional helper table for "sent" state (idempotency)
        s.execute("""
        CREATE TABLE IF NOT EXISTS job_sent (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
            feed_event_id BIGINT NOT NULL REFERENCES feed_event(id) ON DELETE CASCADE,
            sent_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC') NOT NULL
        );
        """)
        s.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname='ux_job_sent_user_event'
            ) THEN
                CREATE UNIQUE INDEX ux_job_sent_user_event ON job_sent(user_id, feed_event_id);
            END IF;
        END$$;
        """)

        s.commit()
