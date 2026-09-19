-- WhatsApp study dashboard schema for TimescaleDB.
-- Run once against the dashboard database:
--   psql postgresql://postgres:password@localhost:5432/postgres -f dashboard/schema.sql
-- Safe to re-run: everything is IF NOT EXISTS.

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- One row per participant, upserted by the poller on every change.
-- phone_hash is a salted SHA-256 prefix; the raw number never enters this DB.
CREATE TABLE IF NOT EXISTS wa_conversations (
    phone_hash           TEXT PRIMARY KEY,
    variant              TEXT,            -- e.g. A_control_condition
    prompt_variant       TEXT,            -- e.g. PT_prompt_A_control_condition
    language             TEXT,
    phase                TEXT,            -- awaiting_initial_rating | normal | awaiting_check_in_rating | ended
    intro_sent           BOOLEAN,
    started_at           TIMESTAMPTZ,     -- Meta timestamp of the first message, else first stored message
    last_user_msg_at     TIMESTAMPTZ,
    last_assistant_msg_at TIMESTAMPTZ,
    last_activity_at     TIMESTAMPTZ,     -- Firestore updated_at
    debriefed_at         TIMESTAMPTZ,
    user_turn_count      INTEGER,
    n_messages           INTEGER,
    n_ratings            INTEGER,
    initial_rating       INTEGER,
    latest_rating        INTEGER,
    n_referrals          INTEGER,
    ad_source_id         TEXT,            -- first referral's ad id
    ad_source_type       TEXT,
    ctwa_clid            TEXT,            -- first referral's click id
    synced_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS wa_conversations_started_idx   ON wa_conversations (started_at);
CREATE INDEX IF NOT EXISTS wa_conversations_debriefed_idx ON wa_conversations (debriefed_at);
CREATE INDEX IF NOT EXISTS wa_conversations_phase_idx     ON wa_conversations (phase);

-- One row per stored message (user and assistant). Append-only.
CREATE TABLE IF NOT EXISTS wa_messages (
    ts          TIMESTAMPTZ NOT NULL,
    phone_hash  TEXT NOT NULL,
    turn_index  INTEGER NOT NULL,        -- position in the Firestore history array
    role        TEXT NOT NULL,           -- user | assistant
    n_chars     INTEGER,
    variant     TEXT,
    UNIQUE (phone_hash, turn_index, ts)
);
SELECT create_hypertable('wa_messages', by_range('ts'), if_not_exists => TRUE);

-- One row per trust rating.
CREATE TABLE IF NOT EXISTS wa_ratings (
    ts             TIMESTAMPTZ NOT NULL,
    phone_hash     TEXT NOT NULL,
    message_index  INTEGER NOT NULL,     -- 0 = initial rating
    score          INTEGER NOT NULL,
    variant        TEXT,
    UNIQUE (phone_hash, message_index, ts)
);
SELECT create_hypertable('wa_ratings', by_range('ts'), if_not_exists => TRUE);

-- Sampled gauges, one row per poll tick (zeros included so Grafana draws a
-- flat line when nothing is happening).
CREATE TABLE IF NOT EXISTS rt_metrics (
    logged_at            TIMESTAMPTZ NOT NULL,
    active_5m            INTEGER NOT NULL,   -- not ended, last message within 5 min
    active_30m           INTEGER NOT NULL,   -- not ended, last message within 30 min
    awaiting_rating      INTEGER NOT NULL,   -- blocked on a trust-rating reply
    phase_initial        INTEGER NOT NULL,
    phase_normal         INTEGER NOT NULL,
    phase_checkin        INTEGER NOT NULL,
    phase_ended          INTEGER NOT NULL,
    total_conversations  INTEGER NOT NULL,
    started_last_hour    INTEGER NOT NULL,
    debriefed_last_hour  INTEGER NOT NULL
);
SELECT create_hypertable('rt_metrics', by_range('logged_at'), if_not_exists => TRUE);

-- Dashboard setting: how long a conversation may be silent before it counts
-- as abandoned. Kept in the database (not as a Grafana variable) so that
-- public/shared dashboards, which cannot use template variables, still work.
-- To change it, re-run this statement with a different interval.
CREATE OR REPLACE FUNCTION abandon_after() RETURNS interval
    LANGUAGE sql IMMUTABLE AS $$ SELECT interval '24 hours' $$;

-- Poller bookkeeping (Firestore updated_at watermark).
CREATE TABLE IF NOT EXISTS poller_state (
    key    TEXT PRIMARY KEY,
    value  TEXT
);
