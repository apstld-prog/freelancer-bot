-- Table used to prevent sending duplicate jobs per user
CREATE TABLE IF NOT EXISTS sent_job (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    job_key TEXT NOT NULL,
    sent_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC')
);

-- Ensure quick lookups for (user_id, job_key)
CREATE UNIQUE INDEX IF NOT EXISTS idx_sent_job_user_job ON sent_job(user_id, job_key);
