#!/usr/bin/env python3
"""
init_sent_table.py — one-time script to create the sent_job table safely.
It uses the DATABASE_URL from your Render environment.
"""

import os
import psycopg2

sql = """
CREATE TABLE IF NOT EXISTS sent_job (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    job_key TEXT NOT NULL,
    sent_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC')
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sent_job_user_job
    ON sent_job(user_id, job_key);
"""

def main():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("❌ DATABASE_URL not found. Make sure it's set in Render environment.")
    print("Connecting to database...")
    conn = psycopg2.connect(url.replace("postgresql+psycopg2://", "postgresql://"))
    with conn, conn.cursor() as cur:
        cur.execute(sql)
    conn.close()
    print("✅ sent_job table verified/created successfully.")

if __name__ == "__main__":
    main()
