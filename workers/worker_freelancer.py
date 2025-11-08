import logging
import time
import requests
from db import get_session
from db_keywords import list_keywords
from db_events import record_event
from utils import get_all_active_users

log = logging.getLogger("worker.freelancer")

API_URL = "https://www.freelancer.com/api/projects/0.1/projects/active/"


def run_freelancer_worker():
    log.info("🚀 Starting freelancer worker...")

    while True:
        try:
            with get_session() as s:
                users = get_all_active_users(s)

                for u in users:
                    user_id = u.id       # ✅ FIX
                    kws = list_keywords(user_id)  # ✅ FIX

                    if not kws:
                        continue

                    query = ",".join(kws)

                    r = requests.get(
                        API_URL,
                        params={
                            "query": query,
                            "limit": 20,
                            "full_description": False,
                            "job_details": False,
                            "sort_field": "time_submitted",
                            "sort_direction": "desc"
                        },
                        timeout=15
                    )

                    if r.status_code != 200:
                        continue

                    data = r.json()
                    projects = data.get("result", {}).get("projects", [])

                    for p in projects:
                        record_event(
                            user_id=user_id,
                            platform="freelancer",
                            title=p.get("title"),
                            description=p.get("preview_description"),
                            affiliate_url=None,
                            original_url=f"https://www.freelancer.com/projects/{p.get('id')}",
                            budget_amount=p.get("budget", {}).get("minimum"),
                            budget_currency="USD",
                            keyword=query
                        )

        except Exception as e:
            log.error(f"Error in worker loop: {e}")

        time.sleep(60)

