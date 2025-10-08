import asyncio, os, httpx
from db import SessionLocal, User, Keyword, init_db

FREELANCER_API = "https://www.freelancer.com/api/projects/0.1/projects/active/"

async def fetch_jobs(query: str):
    params = {
        "query": query, "limit": 10, "compact": "true",
        "user_details": "true", "job_details": "true"
    }
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(FREELANCER_API, params=params)
        r.raise_for_status()
        return r.json().get("result", {}).get("projects", [])

async def cycle_once():
    db = SessionLocal()
    try:
        users = db.query(User).all()
        for u in users:
            if not u.is_active or u.is_blocked:
                continue
            for kw in db.query(Keyword).filter(Keyword.user_id == u.id):
                await fetch_jobs(kw.value)
    finally:
        db.close()

async def main():
    init_db()
    while True:
        await cycle_once()
        await asyncio.sleep(120)

if __name__ == "__main__":
    asyncio.run(main())
