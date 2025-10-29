from db import get_session


def ensure_feed_events_schema():
    """
    Δημιουργεί τον πίνακα feed_event αν δεν υπάρχει ήδη.
    Παρακολουθεί κάθε fetch από τις πλατφόρμες (Freelancer, PPH, Skywalker).
    """
    with get_session() as s:
        s.execute("""
        CREATE TABLE IF NOT EXISTS feed_event (
            id SERIAL PRIMARY KEY,
            platform TEXT NOT NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC')
        );
        """)
        s.commit()


def record_event(platform: str):
    """
    Καταγράφει νέο event στο feed_event όταν γίνεται επιτυχής fetch.
    """
    if not platform:
        return

    with get_session() as s:
        s.execute(
            "INSERT INTO feed_event (platform) VALUES (%s);",
            (platform,)
        )
        s.commit()


def get_platform_stats(window_hours: int = 24):
    """
    Επιστρέφει dictionary με αριθμό events ανά πλατφόρμα
    εντός του τελευταίου window_hours (default: 24 ώρες).
    Παράδειγμα:
      {'Freelancer': 120, 'PeoplePerHour': 25, 'Skywalker': 3}
    """
    with get_session() as s:
        s.execute("""
        SELECT platform, COUNT(*) AS cnt
        FROM feed_event
        WHERE created_at >= (NOW() AT TIME ZONE 'UTC') - (%s || ' hours')::INTERVAL
        GROUP BY platform
        ORDER BY cnt DESC;
        """, (str(window_hours),))
        rows = s.fetchall()

        # Επιστρέφει σε μορφή dict
        return {r["platform"]: r["cnt"] for r in rows}


def get_total_stats():
    """
    Επιστρέφει συνολικό πλήθος events ανά πλατφόρμα από την αρχή.
    Παράδειγμα:
      {'Freelancer': 980, 'PeoplePerHour': 45}
    """
    with get_session() as s:
        s.execute("""
        SELECT platform, COUNT(*) AS cnt
        FROM feed_event
        GROUP BY platform
        ORDER BY cnt DESC;
        """)
        rows = s.fetchall()

        return {r["platform"]: r["cnt"] for r in rows}


def cleanup_old_events(max_days: int = 7):
    """
    Διαγράφει παλιά feed events (προαιρετική συντήρηση).
    Κρατάει μόνο τα τελευταία N days (default: 7).
    """
    with get_session() as s:
        s.execute("""
        DELETE FROM feed_event
        WHERE created_at < (NOW() AT TIME ZONE 'UTC') - (%s || ' days')::INTERVAL;
        """, (str(max_days),))
        s.commit()


if __name__ == "__main__":
    print("======================================================")
    print("🧩 FEED EVENTS SCHEMA INITIALIZER")
    print("======================================================")
    ensure_feed_events_schema()
    print("✅ feed_event schema ensured successfully.")
    print("======================================================")
