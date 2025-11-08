import logging
from sqlalchemy import text
from db import engine

log = logging.getLogger("db_events")


def ensure_feed_events_schema():
    """
    Ensures the feed_event table exists.
    Safe to run many times.
    """
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS feed_event (
                id SERIAL PRIMARY KEY,
                platform VARCHAR(50) NOT NULL,
                external_id VARCHAR(255) NOT NULL,
                title TEXT,
                description TEXT,
                affiliate_url TEXT,
                original_url TEXT,
                budget_amount FLOAT,
                budget_currency VARCHAR(20),
                budget_usd FLOAT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))

    log.info("✅ feed_event table ensured.")


def record_event(platform: str, external_id: str, title: str = None,
                 description: str = None, affiliate_url: str = None,
                 original_url: str = None, budget_amount=None,
                 budget_currency=None, budget_usd=None):
    """
    Insert a new job event into feed_event.
    Workers call this when sending jobs.
    """
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO feed_event (
                platform, external_id, title, description,
                affiliate_url, original_url,
                budget_amount, budget_currency, budget_usd
            )
            VALUES (
                :platform, :external_id, :title, :description,
                :affiliate_url, :original_url,
                :budget_amount, :budget_currency, :budget_usd
            );
        """), {
            "platform": platform,
            "external_id": external_id,
            "title": title,
            "description": description,
            "affiliate_url": affiliate_url,
            "original_url": original_url,
            "budget_amount": budget_amount,
            "budget_currency": budget_currency,
            "budget_usd": budget_usd
        })

    return True
