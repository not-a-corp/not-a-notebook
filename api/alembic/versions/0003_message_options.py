"""A question can carry options the user may click

Revision ID: 0003
Revises: 0002

The agent offers a few replies with its question; the user picks one or writes
their own. Kept with the message so a screen reloaded later shows the same
buttons. Questions asked before this have none.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    sql = """
        ALTER TABLE messages
            ADD COLUMN options JSONB
    """
    op.execute(sql)

    sql = """
        UPDATE messages m
           SET options = '[]'::jsonb
         WHERE m.kind = 'question'
    """
    op.execute(sql)

    sql = """
        ALTER TABLE messages
            ADD CONSTRAINT messages_options_only_on_questions
                CHECK (options IS NULL OR kind = 'question')
    """
    op.execute(sql)


def downgrade() -> None:
    sql = """
        ALTER TABLE messages
            DROP CONSTRAINT messages_options_only_on_questions,
            DROP COLUMN options
    """
    op.execute(sql)
