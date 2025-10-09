# db_events.py — job events storage, upsert with affiliate preference, platform stats
from __future__ import annotations
from typing import Iterable, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
import hashlib

from sqlalchemy import text
from db import get_session

# Preferred sources (affiliate-first)
AFFILIATE_PLATFORMS = {
    "Freelancer", "PeoplePerHour", "Malt", "Workana", "Wripple", "Toptal",
    "twago", "freelancermap", "YunoJuno", "Worksome", "Codeable", "Guru", "99designs"
}

def _hash_for(title: str, original_url: str) -> str:
    key = (title or "").strip().lower() + "||" + (original_url or "").strip().lower()
    return hashlib.sha1(key.encode("utf-8")).hexdigest()

def ensure_feed_events_schema() -> None:
    """Create table & indexes if missing; compatible with previous runs."""
    with get_session() as s:
        s.execute(text("""
        CREATE TABLE IF NOT EXISTS job_event (
            id SERIAL PRIMARY KEY,
            platform TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            original_url TEXT NOT NULL,
            affiliate_url TEXT,
            source_url TEXT,
            country TEXT,
            budget_amount NUMERIC,
            budget_currency TEXT,
            posted_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
            hash TEXT NOT NULL UNIQUE
        )
        """))
        s.execute(text("CREATE INDEX IF NOT EXISTS idx_job_event_created_at ON job_event (created_at DESC)"))
        s.execute(text("CREATE INDEX IF NOT EXISTS idx_job_event_platform ON job_event (platform)"))
        s.commit()

def upsert_events(events: Iterable[Dict[str, Any]]) -> int:
    """
    Insert or update events by unique hash.
    If a duplicate arrives:
      - prefer record that has affiliate_url and/or explicit budget in USD
      - update title/description if longer (more informative)
    Returns number of new rows inserted.
    """
    inserted = 0
    with get_session() as s:
        for e in events:
            title = (e.get("title") or "").strip()
            original_url = (e.get("original_url") or "").strip()
            if not title or not original_url:
                continue
            h = e.get("hash") or _hash_for(title, original_url)

            # Try insert
            res = s.execute(text("""
                INSERT INTO job_event
                (platform, title, description, original_url, affiliate_url, source_url, country,
                 budget_amount, budget_currency, posted_at, hash)
                VALUES (:platform, :title, :description, :original_url, :affiliate_url, :source_url, :country,
                        :budget_amount, :budget_currency, :posted_at, :hash)
                ON CONFLICT (hash) DO NOTHING
            """), {
                "platform": e.get("platform"),
                "title": title,
                "description": e.get("description"),
                "original_url": original_url,
                "affiliate_url": e.get("affiliate_url"),
                "source_url": e.get("source_url"),
                "country": e.get("country"),
                "budget_amount": e.get("budget_amount"),
                "budget_currency": e.get("budget_currency"),
                "posted_at": e.get("posted_at"),
                "hash": h
            })
            if getattr(res, "rowcount", 0) == 1:
                inserted += 1
                continue

            # Conflict: decide if update is better (affiliate preference or richer info)
            row = s.execute(text("SELECT id, platform, affiliate_url, title, description, budget_currency FROM job_event WHERE hash=:h"),
                            {"h": h}).fetchone()
            if not row:
                continue

            cur_aff = bool(row[2])
            new_aff = bool(e.get("affiliate_url"))
            better_aff = (not cur_aff and new_aff)

            cur_title = row[3] or ""
            cur_desc = row[4] or ""
            new_title = title
            new_desc = e.get("description") or ""
            richer_text = (len(new_title) + len(new_desc)) > (len(cur_title) + len(cur_desc))

            # Prefer affiliate or richer text
            if better_aff or richer_text:
                s.execute(text("""
                    UPDATE job_event
                    SET platform=:platform,
                        title=:title,
                        description=:description,
                        affiliate_url=COALESCE(:affiliate_url, affiliate_url),
                        source_url=COALESCE(:source_url, source_url),
                        country=COALESCE(:country, country),
                        budget_amount=COALESCE(:budget_amount, budget_amount),
                        budget_currency=COALESCE(:budget_currency, budget_currency),
                        posted_at=COALESCE(:posted_at, posted_at)
                    WHERE hash=:hash
                """), {
                    "platform": e.get("platform"),
                    "title": title,
                    "description": new_desc or None,
                    "affiliate_url": e.get("affiliate_url"),
                    "source_url": e.get("source_url"),
                    "country": e.get("country"),
                    "budget_amount": e.get("budget_amount"),
                    "budget_currency": e.get("budget_currency"),
                    "posted_at": e.get("posted_at"),
                    "hash": h
                })
        s.commit()
    return inserted

def get_platform_stats(hours: int) -> Dict[str, int]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    with get_session() as s:
        rows = s.execute(text("""
            SELECT platform, COUNT(*) FROM job_event
            WHERE created_at >= :since
            GROUP BY platform
            ORDER BY COUNT(*) DESC
        """), {"since": since}).fetchall()
    return {r[0]: int(r[1]) for r in rows}
