"""Messages say whether the analyst answered or asked, and keep the grounding check

Revision ID: 0002
Revises: 0001

Both were only in the run's events, so a screen reloaded later could not tell a
question from an answer, nor show an answer's grounding badge. Existing rows
are filled from what the runs already recorded.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    sql = """
        ALTER TABLE messages
            ADD COLUMN kind VARCHAR(10),
            ADD COLUMN grounding JSONB
    """
    op.execute(sql)

    # A question ends its run 'awaiting_user'; every other analyst message is an
    # answer — including one whose run is gone.
    sql = """
        UPDATE messages m
           SET kind = CASE WHEN r.status = 'awaiting_user' THEN 'question' ELSE 'answer' END
          FROM runs r
         WHERE m.role = 'assistant'
           AND r.id = m.run_id
    """
    op.execute(sql)

    sql = """
        UPDATE messages m
           SET kind = 'answer'
         WHERE m.role = 'assistant'
           AND m.kind IS NULL
    """
    op.execute(sql)

    # The check was stored as the run's grounding.checked event.
    sql = """
        UPDATE messages m
           SET grounding = jsonb_build_object(
                   'numbers', e.event -> 'numbers',
                   'found', e.event -> 'found',
                   'unfound', e.event -> 'unfound'
               )
          FROM run_events e
         WHERE m.kind = 'answer'
           AND e.run_id = m.run_id
           AND e.type = 'grounding.checked'
    """
    op.execute(sql)

    sql = """
        ALTER TABLE messages
            ADD CONSTRAINT messages_kind_follows_role
                CHECK ((role = 'user' AND kind IS NULL)
                    OR (role = 'assistant' AND kind IN ('answer', 'question'))),
            ADD CONSTRAINT messages_grounding_only_on_answers
                CHECK (grounding IS NULL OR kind = 'answer')
    """
    op.execute(sql)


def downgrade() -> None:
    sql = """
        ALTER TABLE messages
            DROP CONSTRAINT messages_grounding_only_on_answers,
            DROP CONSTRAINT messages_kind_follows_role,
            DROP COLUMN grounding,
            DROP COLUMN kind
    """
    op.execute(sql)
