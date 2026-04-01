-- 001_create_jobs_table.sql
-- Job queue table for staffNinja background tasks

CREATE TABLE IF NOT EXISTS staffninja_jobs (
    id              SERIAL PRIMARY KEY,
    job_type        VARCHAR(100)    NOT NULL,
    payload         JSONB           NOT NULL DEFAULT '{}',
    status          VARCHAR(20)     NOT NULL DEFAULT 'pending',
    result          JSONB,
    error           TEXT,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_by      BIGINT,                             -- Discord user snowflake
    max_retries     INT             NOT NULL DEFAULT 3,
    attempt         INT             NOT NULL DEFAULT 0
);

-- Fast lookup for the worker poll query
CREATE INDEX IF NOT EXISTS idx_jobs_status_created
    ON staffninja_jobs (status, created_at);
