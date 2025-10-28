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

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO postgres;

