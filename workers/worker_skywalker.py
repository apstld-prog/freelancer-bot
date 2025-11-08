import logging
import time
import requests
from db import get_session
from db_keywords import list_keywords
from db_events import record_event
from utils import get_all_active_users

log = logging.getLogger("worker.skywalker")

API_URL = "https://www.skywalker.gr/el/aggelies"


def run_skywalker_worker():
    log.info("🚀 Starting skywalker worker...")

    while True:
        try:
            with get_session() as s:
                users = get_all_active_users(s)

                for u in users:
                    user_id = u.id        # ✅ FIX
                    kws = list_keywords(user_id)  # ✅ FIX

                    if not kws:
                        continue

                    for kw in kws:
                        # Placeholder – δικό σου parsing
                        record_event(
                            user_id=user_id,
                            platform="skywalker",
                            title=f"Skywalker result for {kw}",
                            description="",
                            affiliate_url=None,
                            original_url="https://www.skywalker.gr/",
                            budget_amount=None,
                            budget_currency=None,
                            keyword=kw
                        )

        except Exception as e:
            log.error(f"Error in worker loop: {e}")

        time.sleep(60)

