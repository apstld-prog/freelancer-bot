#!/usr/bin/env python3
# platform_skywalker.py — RSS fetcher for Skywalker.gr jobs
import feedparser
import logging
from html import unescape

log = logging.getLogger("skywalker")

def fetch(feed_url: str):
    """Fetch RSS feed from Skywalker.gr"""
    items = []
    try:
        feed = feedparser.parse(feed_url)
        for e in feed.entries:
            title = unescape(e.get("title", "").strip())
            link = e.get("link", "").strip()
            desc = unescape(e.get("summary", "").strip())
            published = e.get("published_parsed")
            ts = None
            try:
                import time
                if published:
                    ts = int(time.mktime(published))
            except Exception:
                ts = None
            items.append({
                "title": title,
                "description": desc,
                "original_url": link,
                "source": "Skywalker",
                "time_submitted": ts
            })
        log.info("Skywalker fetched %d jobs", len(items))
    except Exception as e:
        log.warning("Skywalker fetch error: %s", e)
    return items


# --- ✅ Compatibility alias for worker_runner ---
fetch_skywalker_jobs = fetch
