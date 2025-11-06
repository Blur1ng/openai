\connect prompt_db;
GRANT ALL PRIVILEGES ON DATABASE prompt_db TO postgres;
CREATE TABLE prompt_data (
    id           BIGSERIAL PRIMARY KEY,
    ai_model     TEXT NOT NULL,
    prompt_name  TEXT NOT NULL,
    prompt       TEXT NOT NULL,
    request      TEXT NOT NULL,
    model        TEXT NOT NULL
);

CREATE TABLE request_data (
    id           BIGSERIAL PRIMARY KEY,
    ai_model     TEXT NOT NULL,
    request      TEXT NOT NULL,
    model        TEXT NOT NULL
);

CREATE TABLE prompts (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    content         TEXT NOT NULL,
    description     TEXT,
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_prompts_name ON prompts(name);
CREATE INDEX idx_prompts_is_active ON prompts(is_active);

CREATE TABLE job_results (
    id              BIGSERIAL PRIMARY KEY,
    job_id          TEXT NOT NULL UNIQUE,
    batch_id        TEXT NOT NULL,
    ai_model        TEXT NOT NULL,
    model           TEXT NOT NULL,
    prompt_name     TEXT NOT NULL,
    request_code    TEXT NOT NULL,
    result_text     TEXT,
    prompt_tokens   INTEGER,
    completion_tokens INTEGER,
    total_tokens    INTEGER,
    status          TEXT NOT NULL DEFAULT 'queued',
    error_message   TEXT,
    created_at      TIMESTAMP DEFAULT NOW(),
    completed_at    TIMESTAMP
);

CREATE INDEX idx_job_results_job_id ON job_results(job_id);
CREATE INDEX idx_job_results_batch_id ON job_results(batch_id);
CREATE INDEX idx_job_results_created_at ON job_results(created_at);

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO postgres;

