"""Initial schema: everything in schema.sql

Revision ID: 0001
Revises:

Each statement is copied from schema.sql, which is where the reasons live. The
drift test proves the two build the same database.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _create_set_updated_at()
    _create_users()
    _create_oauth_accounts()
    _create_sessions()
    _create_models()
    _create_conversations()
    _create_runs()
    _create_run_events()
    _create_files()
    _create_messages()
    _create_cells()
    _create_cell_outputs()


def downgrade() -> None:
    sql = """
        DROP TABLE cell_outputs,
                   cells,
                   messages,
                   files,
                   run_events,
                   runs,
                   conversations,
                   models,
                   sessions,
                   oauth_accounts,
                   users
    """
    op.execute(sql)

    sql = """
        DROP FUNCTION set_updated_at()
    """
    op.execute(sql)


def _create_set_updated_at() -> None:
    # Flush left and byte-identical to schema.sql: PostgreSQL stores a function
    # body verbatim, so indenting this would show up as a difference in the drift
    # test.
    sql = """\
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""
    op.execute(sql)


def _create_users() -> None:
    sql = """
        CREATE TABLE users (
            id            SERIAL       PRIMARY KEY,
            external_id   UUID         NOT NULL UNIQUE DEFAULT uuidv7(),
            email         VARCHAR(255) NOT NULL,
            password_hash VARCHAR(255),
            created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
        )
    """
    op.execute(sql)

    sql = """
        CREATE UNIQUE INDEX users_email_lower_key ON users (lower(email))
    """
    op.execute(sql)

    sql = """
        CREATE TRIGGER users_set_updated_at
            BEFORE UPDATE ON users FOR EACH ROW
            WHEN (OLD.* IS DISTINCT FROM NEW.*)
            EXECUTE FUNCTION set_updated_at()
    """
    op.execute(sql)


def _create_oauth_accounts() -> None:
    sql = """
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
        )
    """
    op.execute(sql)


def _create_sessions() -> None:
    sql = """
        CREATE TABLE sessions (
            id                  SERIAL      PRIMARY KEY,
            token_hash          BYTEA       NOT NULL UNIQUE,
            user_id             INTEGER     NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            expires_at          TIMESTAMPTZ NOT NULL,
            absolute_expires_at TIMESTAMPTZ NOT NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT sessions_absolute_after_sliding
                CHECK (absolute_expires_at >= expires_at)
        )
    """
    op.execute(sql)

    sql = """
        CREATE INDEX sessions_user_id_idx ON sessions (user_id)
    """
    op.execute(sql)


def _create_models() -> None:
    sql = """
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
        )
    """
    op.execute(sql)

    sql = """
        CREATE INDEX models_user_id_idx ON models (user_id)
    """
    op.execute(sql)

    sql = """
        CREATE TRIGGER models_set_updated_at
            BEFORE UPDATE ON models FOR EACH ROW
            WHEN (OLD.* IS DISTINCT FROM NEW.*)
            EXECUTE FUNCTION set_updated_at()
    """
    op.execute(sql)


def _create_conversations() -> None:
    sql = """
        CREATE TABLE conversations (
            id          SERIAL       PRIMARY KEY,
            external_id UUID         NOT NULL UNIQUE DEFAULT uuidv7(),
            user_id     INTEGER      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            model_id    INTEGER      REFERENCES models (id) ON DELETE SET NULL,
            title       VARCHAR(200) NOT NULL DEFAULT 'Untitled',
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
        )
    """
    op.execute(sql)

    sql = """
        CREATE INDEX conversations_user_id_updated_at_idx
            ON conversations (user_id, updated_at DESC)
    """
    op.execute(sql)

    sql = """
        CREATE TRIGGER conversations_set_updated_at
            BEFORE UPDATE ON conversations FOR EACH ROW
            WHEN (OLD.* IS DISTINCT FROM NEW.*)
            EXECUTE FUNCTION set_updated_at()
    """
    op.execute(sql)


def _create_runs() -> None:
    sql = """
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
        )
    """
    op.execute(sql)

    sql = """
        CREATE UNIQUE INDEX runs_one_running_per_conversation
            ON runs (conversation_id)
            WHERE status = 'running'
    """
    op.execute(sql)

    sql = """
        CREATE INDEX runs_conversation_id_idx ON runs (conversation_id)
    """
    op.execute(sql)


def _create_run_events() -> None:
    sql = """
        CREATE TABLE run_events (
            run_id     INTEGER     NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
            seq        INTEGER     NOT NULL,
            type       VARCHAR(50) NOT NULL,
            event      JSONB       NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

            PRIMARY KEY (run_id, seq),

            CONSTRAINT run_events_seq_positive
                CHECK (seq >= 1)
        )
    """
    op.execute(sql)


def _create_files() -> None:
    sql = """
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
        )
    """
    op.execute(sql)


def _create_messages() -> None:
    sql = """
        CREATE TABLE messages (
            id              SERIAL      PRIMARY KEY,
            external_id     UUID        NOT NULL UNIQUE DEFAULT uuidv7(),
            conversation_id INTEGER     NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
            run_id          INTEGER     REFERENCES runs (id) ON DELETE SET NULL,
            role            VARCHAR(10) NOT NULL,
            text            TEXT        NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT messages_role_known
                CHECK (role IN ('user', 'assistant'))
        )
    """
    op.execute(sql)

    sql = """
        CREATE INDEX messages_conversation_id_created_at_idx
            ON messages (conversation_id, created_at)
    """
    op.execute(sql)


def _create_cells() -> None:
    sql = """
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
        )
    """
    op.execute(sql)

    sql = """
        CREATE TRIGGER cells_set_updated_at
            BEFORE UPDATE ON cells FOR EACH ROW
            WHEN (OLD.* IS DISTINCT FROM NEW.*)
            EXECUTE FUNCTION set_updated_at()
    """
    op.execute(sql)


def _create_cell_outputs() -> None:
    sql = """
        CREATE TABLE cell_outputs (
            cell_id INTEGER     NOT NULL REFERENCES cells (id) ON DELETE CASCADE,
            ordinal INTEGER     NOT NULL,
            kind    VARCHAR(10) NOT NULL,
            payload JSONB       NOT NULL,

            PRIMARY KEY (cell_id, ordinal),

            CONSTRAINT cell_outputs_kind_known
                CHECK (kind IN ('stream', 'error', 'plotly', 'table', 'text', 'image'))
        )
    """
    op.execute(sql)
