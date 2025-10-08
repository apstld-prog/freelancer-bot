import asyncio
import os
from datetime import datetime, timezone
import httpx

from db import SessionLocal, User, Keyword, init_db

FREELANCER_API = "https://www.freelancer.com/api/projects/0.1/projects/active/"

def now_utc():
    return datetime.now(timezone.utc)

async def fetch_freelancer(query: str) -> list[dict]:
    params = {
        "query": query,
        "limit": 30,
        "compact": "true",
        "user_details": "true",
        "job_details": "true",
        "full_description": "true",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(FREELANCER_API, params=params)
        r.raise_for_status()
        data = r.json()
        return data.get("result", {}).get("projects", []) or []

async def cycle_once():
    db = SessionLocal()
    try:
        users = db.query(User).all()
        for u in users:
            if not u.is_active or u.is_blocked:
                continue
            kws = [k.value for k in u.keywords]
            for kw in kws:
                try:
                    _ = await fetch_freelancer(kw)
                    # εδώ θα έμπαινε η λογική match & send
                except Exception:
                    pass
    finally:
        db.close()

async def main_loop():
    init_db()
    interval = int(os.getenv("WORKER_INTERVAL", "120"))
    while True:
        try:
            await cycle_once()
        except Exception:
            pass
        await asyncio.sleep(interval)

if __name__ == "__main__":
    asyncio.run(main_loop())
