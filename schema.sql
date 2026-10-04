-- not-a-notebook — target schema. Alembic migrations are what create it.
-- PostgreSQL 18+ (uuidv7).
--
-- Every table a user can reach hangs off users, directly or through a
-- conversation, and every query is scoped by user_id. The serial id never leaves
-- the database; external_id is what the API shows.
--
-- Secret fields are stored encrypted in the form v1.<nonce>.<content>,
-- AES-256-GCM, with the key coming from SECRETS_KEY in the environment.


CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ── identity ─────────────────────────────────────────────────────────────────


CREATE TABLE users (
    id            SERIAL       PRIMARY KEY,
    external_id   UUID         NOT NULL UNIQUE DEFAULT uuidv7(),
    email         VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- password_hash is NULL for an account created through OAuth until a password is
-- set. Nothing else tells the two kinds apart.
CREATE UNIQUE INDEX users_email_lower_key ON users (lower(email));

CREATE TRIGGER users_set_updated_at
    BEFORE UPDATE ON users FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
    EXECUTE FUNCTION set_updated_at();


CREATE TABLE oauth_accounts (
    id         SERIAL       PRIMARY KEY,
    user_id    INTEGER      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    provider   VARCHAR(20)  NOT NULL,
    subject    VARCHAR(255) NOT NULL,
    email      VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT oauth_accounts_provider_known
        CHECK (provider IN ('google', 'github')),
    CONSTRAINT oauth_accounts_provider_subject_key
        UNIQUE (provider, subject),
    CONSTRAINT oauth_accounts_one_per_provider
        UNIQUE (user_id, provider)
);

-- subject is the provider's own user id, which survives the user changing their
-- email there. email is a copy from sign-in time, for display only — identity is
-- (provider, subject), never the email.


CREATE TABLE sessions (
    id                  SERIAL      PRIMARY KEY,
    token_hash          BYTEA       NOT NULL UNIQUE,
    user_id             INTEGER     NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    expires_at          TIMESTAMPTZ NOT NULL,
    absolute_expires_at TIMESTAMPTZ NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT sessions_absolute_after_sliding
        CHECK (absolute_expires_at >= expires_at)
);

-- One row per signed-in device. token_hash is the SHA-256 of the refresh token;
-- the token itself is never stored. Rotation replaces token_hash in place, so the
-- old token stops matching the moment the new one exists. expires_at slides on
-- every refresh, absolute_expires_at does not.
CREATE INDEX sessions_user_id_idx ON sessions (user_id);


-- ── models ───────────────────────────────────────────────────────────────────


CREATE TABLE models (
    id                SERIAL       PRIMARY KEY,
    external_id       UUID         NOT NULL UNIQUE DEFAULT uuidv7(),
    user_id           INTEGER      REFERENCES users (id) ON DELETE CASCADE,
    env_name          VARCHAR(100) UNIQUE,
    name              VARCHAR(100) NOT NULL,
    adapter           VARCHAR(30)  NOT NULL,
    base_url          TEXT,
    model             VARCHAR(255) NOT NULL,
    dialect           VARCHAR(10)  NOT NULL,
    api_key_encrypted TEXT,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT models_adapter_known
        CHECK (adapter IN ('anthropic', 'openai_responses', 'openai_compatible')),
    CONSTRAINT models_dialect_known
        CHECK (dialect IN ('tools', 'text')),
    CONSTRAINT models_compatible_has_base_url
        CHECK (adapter <> 'openai_compatible' OR base_url IS NOT NULL),
    CONSTRAINT models_owner_or_environment
        CHECK ((user_id IS NULL) = (env_name IS NOT NULL)),
    CONSTRAINT models_environment_stores_no_key
        CHECK (user_id IS NOT NULL OR api_key_encrypted IS NULL),
    CONSTRAINT models_key_looks_encrypted
        CHECK (api_key_encrypted IS NULL OR api_key_encrypted LIKE 'v1.%')
);

-- A row is either a user's (user_id set) or the instance's (env_name set), never
-- both. Environment rows are upserted by env_name on startup so they have a stable
-- id that conversations can point at — but their key is read from the environment
-- on every call and never copied here.
CREATE INDEX models_user_id_idx ON models (user_id);

CREATE TRIGGER models_set_updated_at
    BEFORE UPDATE ON models FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
    EXECUTE FUNCTION set_updated_at();


-- ── conversations ────────────────────────────────────────────────────────────


CREATE TABLE conversations (
    id          SERIAL       PRIMARY KEY,
    external_id UUID         NOT NULL UNIQUE DEFAULT uuidv7(),
    user_id     INTEGER      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    model_id    INTEGER      REFERENCES models (id) ON DELETE SET NULL,
    title       VARCHAR(200) NOT NULL DEFAULT 'Untitled',
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Whether a kernel is running is not stored: kernels live in the runtime, and
-- every one of them is reaped when the API restarts. A column would be wrong the
-- first time the process died.
--
-- updated_at is touched by every message and run, which is what orders the list.
CREATE INDEX conversations_user_id_updated_at_idx ON conversations (user_id, updated_at DESC);

CREATE TRIGGER conversations_set_updated_at
    BEFORE UPDATE ON conversations FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
    EXECUTE FUNCTION set_updated_at();


CREATE TABLE runs (
    id               SERIAL       PRIMARY KEY,
    external_id      UUID         NOT NULL UNIQUE DEFAULT uuidv7(),
    conversation_id  INTEGER      NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    kind             VARCHAR(20)  NOT NULL,
    status           VARCHAR(20)  NOT NULL DEFAULT 'running',
    model_id         INTEGER      REFERENCES models (id) ON DELETE SET NULL,
    model_name       VARCHAR(255),
    tokens_in        INTEGER      NOT NULL DEFAULT 0,
    tokens_out       INTEGER      NOT NULL DEFAULT 0,
    tokens_reasoning INTEGER      NOT NULL DEFAULT 0,
    started_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    finished_at      TIMESTAMPTZ,

    CONSTRAINT runs_kind_known
        CHECK (kind IN ('message', 'profile', 'cell', 'run_all')),
    CONSTRAINT runs_status_known
        CHECK (status IN ('running', 'awaiting_user', 'succeeded',
                          'failed', 'cancelled', 'timed_out')),
    CONSTRAINT runs_finished_when_not_running
        CHECK ((status = 'running') = (finished_at IS NULL)),
    CONSTRAINT runs_message_has_model
        CHECK (kind <> 'message' OR model_name IS NOT NULL)
);

-- A kernel executes one thing at a time, so a conversation has at most one run in
-- progress. This index is that rule: starting a second run is an INSERT that
-- raises UniqueViolation, which becomes CONVERSATION_BUSY — no SELECT first, no
-- race between the check and the insert.
CREATE UNIQUE INDEX runs_one_running_per_conversation
    ON runs (conversation_id)
    WHERE status = 'running';

CREATE INDEX runs_conversation_id_idx ON runs (conversation_id);

-- model_name is copied at the start of the run, so the record keeps saying which
-- model answered after the model row is edited or deleted.
--
-- On startup, any row still 'running' belongs to a process that died. It is
-- closed as 'failed' before the API accepts requests.


CREATE TABLE run_events (
    run_id     INTEGER     NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
    seq        INTEGER     NOT NULL,
    type       VARCHAR(50) NOT NULL,
    event      JSONB       NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (run_id, seq),

    CONSTRAINT run_events_seq_positive
        CHECK (seq >= 1)
);

-- event is the whole envelope exactly as it went down the wire, seq, t and type
-- included. seq and type are repeated as columns so that replay is a range scan
-- on the primary key and nothing has to look inside the JSON.


-- ── what a conversation holds ────────────────────────────────────────────────


CREATE TABLE files (
    id              SERIAL       PRIMARY KEY,
    external_id     UUID         NOT NULL UNIQUE DEFAULT uuidv7(),
    conversation_id INTEGER      NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    bytes           BIGINT       NOT NULL,
    sha256          BYTEA        NOT NULL,
    storage_key     TEXT         NOT NULL UNIQUE,
    profile         JSONB,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT files_name_per_conversation_key
        UNIQUE (conversation_id, name),
    CONSTRAINT files_bytes_positive
        CHECK (bytes > 0)
);

-- name is what the code sees at /data/<name>, so two files with the same name in
-- one conversation would be two files at one path. storage_key is where the
-- FileStore keeps it, and is never shown. profile is NULL until the profiling run
-- writes it.


CREATE TABLE messages (
    id              SERIAL      PRIMARY KEY,
    external_id     UUID        NOT NULL UNIQUE DEFAULT uuidv7(),
    conversation_id INTEGER     NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    run_id          INTEGER     REFERENCES runs (id) ON DELETE SET NULL,
    role            VARCHAR(10) NOT NULL,
    text            TEXT        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    kind            VARCHAR(10),
    grounding       JSONB,

    CONSTRAINT messages_role_known
        CHECK (role IN ('user', 'assistant')),
    CONSTRAINT messages_kind_follows_role
        CHECK ((role = 'user' AND kind IS NULL)
            OR (role = 'assistant' AND kind IN ('answer', 'question'))),
    CONSTRAINT messages_grounding_only_on_answers
        CHECK (grounding IS NULL OR kind = 'answer')
);

-- A user message points at the run it started; an assistant message at the run
-- that produced it. An assistant message is an answer, or a question the agent
-- asked instead of guessing (its run ended 'awaiting_user'); kind says which, so
-- a screen reloaded later can tell them apart without reading the run.
-- grounding is an answer's grounding check ({numbers, found, unfound}), kept
-- with it for the same reason. kind and grounding come last because they were
-- added in 0002, and ALTER TABLE appends.
CREATE INDEX messages_conversation_id_created_at_idx ON messages (conversation_id, created_at);


CREATE TABLE cells (
    id              SERIAL      PRIMARY KEY,
    external_id     UUID        NOT NULL UNIQUE DEFAULT uuidv7(),
    conversation_id INTEGER     NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    run_id          INTEGER     REFERENCES runs (id) ON DELETE SET NULL,
    position        INTEGER     NOT NULL,
    origin          VARCHAR(10) NOT NULL,
    source          TEXT        NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'new',
    stale           BOOLEAN     NOT NULL DEFAULT false,
    attempts        INTEGER     NOT NULL DEFAULT 0,
    execution_count INTEGER,
    executed_at     TIMESTAMPTZ,
    duration_ms     INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT cells_origin_known
        CHECK (origin IN ('agent', 'user')),
    CONSTRAINT cells_status_known
        CHECK (status IN ('new', 'running', 'ok', 'error', 'cancelled')),
    CONSTRAINT cells_position_key
        UNIQUE (conversation_id, position) DEFERRABLE INITIALLY DEFERRED
);

-- Inserting a cell in the middle shifts every position below it by one in a single
-- UPDATE. The unique constraint is DEFERRABLE because, in the middle of that
-- UPDATE, two rows briefly hold the same position — checked at commit, the order
-- is whole again.
--
-- run_id is the run that created the cell, and stays NULL for a cell you wrote.
-- An agent retry replaces source in place and increments attempts; the failed
-- attempts live on in run_events.

CREATE TRIGGER cells_set_updated_at
    BEFORE UPDATE ON cells FOR EACH ROW
    WHEN (OLD.* IS DISTINCT FROM NEW.*)
    EXECUTE FUNCTION set_updated_at();


CREATE TABLE cell_outputs (
    cell_id INTEGER     NOT NULL REFERENCES cells (id) ON DELETE CASCADE,
    ordinal INTEGER     NOT NULL,
    kind    VARCHAR(10) NOT NULL,
    payload JSONB       NOT NULL,

    PRIMARY KEY (cell_id, ordinal),

    CONSTRAINT cell_outputs_kind_known
        CHECK (kind IN ('stream', 'error', 'plotly', 'table', 'text', 'image'))
);

-- Outputs belong to the cell's last execution only: running a cell deletes its
-- outputs and writes the new ones in the same transaction. Earlier executions are
-- in run_events.
