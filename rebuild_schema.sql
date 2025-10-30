cat > rebuild_schema.sql <<'EOF'
-- ======================================================
-- FULL SCHEMA REBUILD (FREELANCER BOT — CLEAN MIGRATION)
-- ======================================================
DROP TABLE IF EXISTS job_sent CASCADE;
DROP TABLE IF EXISTS saved_job CASCADE;
DROP TABLE IF EXISTS user_keywords CASCADE;
DROP TABLE IF EXISTS feed_event CASCADE;
DROP TABLE IF EXISTS "user" CASCADE;

-- 1️⃣ user table
CREATE TABLE "user" (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE,
    trial_until TIMESTAMPTZ NULL,
    access_until TIMESTAMPTZ NULL,
    is_blocked BOOLEAN DEFAULT FALSE NOT NULL,
    is_active  BOOLEAN DEFAULT TRUE  NOT NULL,
    trial_start TIMESTAMPTZ NULL,
    trial_end   TIMESTAMPTZ NULL,
    license_until TIMESTAMPTZ NULL,
    trial_reminder_sent BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC') NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC') NOT NULL,
    started_at TIMESTAMPTZ NULL,
    is_admin   BOOLEAN DEFAULT FALSE NOT NULL,
    countries  TEXT NULL,
    proposal_template TEXT NULL,
    name       TEXT NULL,
    username   TEXT NULL,
    keywords   TEXT NULL
);

-- trigger
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_user_updated_at'
    ) THEN
        CREATE OR REPLACE FUNCTION set_user_updated_at()
        RETURNS TRIGGER AS $BODY$
        BEGIN
            NEW.updated_at := NOW() AT TIME ZONE 'UTC';
            RETURN NEW;
        END;
        $BODY$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_user_updated_at
        BEFORE UPDATE ON "user"
        FOR EACH ROW
        EXECUTE PROCEDURE set_user_updated_at();
    END IF;
END$$;

-- 2️⃣ feed_event table
CREATE TABLE feed_event (
    id BIGSERIAL PRIMARY KEY,
    platform TEXT NOT NULL,
    title TEXT,
    description TEXT,
    affiliate_url TEXT,
    original_url TEXT,
    budget_amount NUMERIC(18,2),
    budget_currency TEXT,
    budget_usd NUMERIC(18,2),
    created_at TIMESTAMPTZ NULL,
    fetched_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC') NOT NULL,
    dedup_key TEXT NULL
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE indexname='ux_feed_event_dedup_key'
    ) THEN
        CREATE UNIQUE INDEX ux_feed_event_dedup_key ON feed_event(dedup_key);
    END IF;
END$$;

-- 3️⃣ saved_job
CREATE TABLE saved_job (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    feed_event_id BIGINT NOT NULL REFERENCES feed_event(id) ON DELETE CASCADE,
    saved_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC') NOT NULL
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE indexname='ux_saved_job_user_feed'
    ) THEN
        CREATE UNIQUE INDEX ux_saved_job_user_feed ON saved_job(user_id, feed_event_id);
    END IF;
END$$;

-- 4️⃣ job_sent
CREATE TABLE job_sent (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    feed_event_id BIGINT NOT NULL REFERENCES feed_event(id) ON DELETE CASCADE,
    sent_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC') NOT NULL
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE indexname='ux_job_sent_user_event'
    ) THEN
        CREATE UNIQUE INDEX ux_job_sent_user_event ON job_sent(user_id, feed_event_id);
    END IF;
END$$;

-- 5️⃣ user_keywords
CREATE TABLE user_keywords (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    keyword TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC') NOT NULL
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE indexname='ux_user_keywords_user_id_keyword'
    ) THEN
        CREATE UNIQUE INDEX ux_user_keywords_user_id_keyword
        ON user_keywords(user_id, keyword);
    END IF;
END$$;

-- default admin keywords
INSERT INTO user_keywords (user_id, keyword)
SELECT 1, kw FROM (VALUES
('logo'), ('lighting'), ('design'), ('sales')
) AS t(kw)
ON CONFLICT DO NOTHING;

-- ✅ schema complete
EOF
