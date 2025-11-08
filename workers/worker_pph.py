import logging
import time
import requests
from db import get_session
from db_keywords import list_keywords
from db_events import record_event
from utils import get_all_active_users

log = logging.getLogger("worker.pph")

API_URL = "https://www.peopleperhour.com/site-search"


def run_pph_worker():
    log.info("🚀 Starting peopleperhour worker...")

    while True:
        try:
            with get_session() as s:
                users = get_all_active_users(s)

                for u in users:
                    user_id = u.id          # ✅ FIX
                    kws = list_keywords(user_id)  # ✅ FIX

                    if not kws:
                        continue

                    for kw in kws:
                        r = requests.get(
                            API_URL,
                            params={"q": kw},
                            timeout=15
                        )

                        if r.status_code != 200:
                            continue

                        html = r.text

                        # Δεν κάνουμε parsing εδώ – placeholder
                        record_event(
                            user_id=user_id,
                            platform="peopleperhour",
                            title=f"Result for {kw}",
                            description="",
                            affiliate_url=None,
                            original_url="https://peopleperhour.com/",
                            budget_amount=None,
                            budget_currency=None,
                            keyword=kw
                        )

        except Exception as e:
            log.error(f"Error in worker loop: {e}")

        time.sleep(60)

