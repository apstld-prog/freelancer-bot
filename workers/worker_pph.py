import os, sys, asyncio, logging

# === FIX: ensure parent dir visible for utils/db imports ===
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import fetch_json, get_all_active_users, send_job_to_user
from db_events import ensure_feed_events_schema, save_feed_event

async def process_jobs():
    logging.info("[PPH] Worker running")
    # your existing peopleperhour scraping logic
