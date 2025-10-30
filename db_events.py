# db_events.py
# Psycopg2-only schema/bootstrap for feed events used by workers/bot
# Includes get_platform_stats() and record_event()

from typing import Optional
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


def record_event(
    platform: str,
    title: str,
    description: Optional[str],
    affiliate_url: str,
    original_url: str,
    budget_amount: Optional[float],
    budget_currency: Optional[str],
    budget_usd: Optional[float],
    created_at: Optional[str],
    dedup_key: Optional[str],
) -> Optional[int]:
    """
    Insert one feed_event safely (ignore duplicates by dedup_key).
    Returns inserted id or None if duplicate.
    """
    with get_session() as s:
        try:
            s.execute(
                """
                INSERT INTO feed_event (
                    platform, title, description, affiliate_url, original_url,
                    budget_amount, budget_currency, budget_usd, created_at, dedup_key
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (dedup_key) DO NOTHING
                RETURNING id;
                """,
                (
                    platform,
                    title,
                    description,
                    affiliate_url,
                    original_url,
                    budget_amount,
                    budget_currency,
                    budget_usd,
                    created_at,
                    dedup_key,
                ),
            )
            row = s.fetchone()
            s.commit()
            return row["id"] if row else None
        except Exception as e:
            print(f"[record_event] ERROR: {e}")
            s.conn.rollback()
            return None


def get_platform_stats() -> dict:
    """
    Return dictionary with total jobs per platform and latest fetched timestamp.
    Example:
        {
            "Freelancer": {"count": 1234, "latest": "2025-10-30T06:20:00Z"},
            "PeoplePerHour": {"count": 200, "latest": "2025-10-30T06:10:00Z"},
            "Skywalker": {"count": 99, "latest": "2025-10-30T06:18:00Z"}
        }
    """
    with get_session() as s:
        s.execute("""
        SELECT platform, COUNT(*) AS count, MAX(fetched_at) AS latest
        FROM feed_event
        GROUP BY platform
        ORDER BY platform;
        """)
        rows = s.fetchall()
    stats = {}
    for r in rows:
        stats[r["platform"]] = {
            "count": int(r["count"]),
            "latest": str(r["latest"]) if r["latest"] else None,
        }
    return stats


if __name__ == "__main__":
    print("======================================================")
    print("📊 INIT FEED EVENTS TOOL — psycopg2 version (FINAL)")
    print("======================================================")
    ensure_feed_events_schema()
    print("✅ feed_event + job_sent tables ensured successfully.")
    print("======================================================")
