import logging
from typing import Optional
from datetime import datetime, timedelta, timezone
from db import get_session

logger = logging.getLogger("db_events")


def ensure_feed_events_schema() -> None:
    with get_session() as s:
        s.execute("""
        CREATE TABLE IF NOT EXISTS feed_event (
            id BIGSERIAL PRIMARY KEY,
            platform TEXT NOT NULL,
            title TEXT,
            description TEXT,
            affiliate_url TEXT,
            original_url  TEXT,
            budget_amount NUMERIC(18,2) NULL,
            budget_currency TEXT NULL,
            budget_usd NUMERIC(18,2) NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
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
        s.execute("""
        CREATE TABLE IF NOT EXISTS job_sent (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
            feed_event_id BIGINT NOT NULL REFERENCES feed_event(id) ON DELETE CASCADE,
            sent_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
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
    title: Optional[str] = None,
    description: Optional[str] = None,
    affiliate_url: Optional[str] = None,
    original_url: Optional[str] = None,
    budget_amount: Optional[float] = None,
    budget_currency: Optional[str] = None,
    budget_usd: Optional[float] = None,
    created_at: Optional[str] = None,
    dedup_key: Optional[str] = None,
) -> Optional[int]:
    """Insert feed_event safely even if only platform is provided."""
    with get_session() as s:
        try:
            if not dedup_key:
                dedup_key = f"{platform}:{original_url or datetime.now(timezone.utc).isoformat()}"

            s.execute(
                """
                INSERT INTO feed_event (
                    platform, title, description, affiliate_url, original_url,
                    budget_amount, budget_currency, budget_usd, created_at, dedup_key
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s, COALESCE(%s, NOW() AT TIME ZONE 'UTC'), %s)
                ON CONFLICT (dedup_key) DO NOTHING
                RETURNING id;
                """,
                (
                    platform,
                    title or "(selftest event)",
                    description or "(no description)",
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
            logger.error(f"[record_event] ERROR: {e}", exc_info=True)
            s.conn.rollback()
            return None


def get_platform_stats(window_hours: int = 24) -> dict:
    """Return per-platform stats within the given time window (hours)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    with get_session() as s:
        s.execute(
            """
            SELECT platform, COUNT(*) AS count, MAX(fetched_at) AS latest
            FROM feed_event
            WHERE fetched_at >= %s
            GROUP BY platform
            ORDER BY platform;
            """,
            (cutoff,),
        )
        rows = s.fetchall()

    stats = {}
    for r in rows:
        stats[r["platform"]] = {
            "count": int(r["count"]),
            "latest": str(r["latest"]) if r["latest"] else None,
        }
    return stats


# Συμβατότητα με legacy workers
def save_feed_event(platform, title, description, original_url, budget, currency):
    try:
        record_event(
            platform=platform,
            title=title,
            description=description,
            affiliate_url=None,
            original_url=original_url,
            budget_amount=budget,
            budget_currency=currency,
            budget_usd=None,
            created_at=None,
            dedup_key=f"{platform}:{original_url}",
        )
    except Exception as e:
        logger.error(f"[save_feed_event] {e}", exc_info=True)


if __name__ == "__main__":
    ensure_feed_events_schema()
    print("✅ feed_event schema ensured")
