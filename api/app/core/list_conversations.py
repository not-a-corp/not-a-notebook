"""The caller's conversations, newest activity first, a page at a time."""

from __future__ import annotations

import math
from collections.abc import Set
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection

from app.core.conversation_row import to_conversation
from app.domain.conversations import ConversationPage, PageMeta


def title_pattern(query: str) -> str:
    """An ILIKE pattern that finds the query anywhere in the title, with the
    query's own % and _ taken literally — "100%" means those four characters."""
    escaped = query.replace("\\", "\\\\")
    escaped = escaped.replace("%", "\\%")
    escaped = escaped.replace("_", "\\_")

    return f"%{escaped}%"


async def list_conversations(
    conn: AsyncConnection[Any],
    user_id: UUID,
    page: int,
    per_page: int,
    query: str | None,
    running: Set[UUID],
) -> ConversationPage:
    pattern = None
    if query is not None:
        pattern = title_pattern(query)

    count_sql = """
        SELECT count(*) AS total
          FROM conversations c
          JOIN users u
            ON u.id = c.user_id
         WHERE u.external_id = %(user_id)s
           AND (%(pattern)s::text IS NULL OR c.title ILIKE %(pattern)s ESCAPE '\\')
    """

    count_params: dict[str, Any] = {
        "user_id": user_id,
        "pattern": pattern,
    }

    # c.id breaks ties, so a page boundary never falls between two rows that
    # could swap places from one request to the next.
    sql = """
        SELECT c.external_id AS id,
               c.title,
               m.external_id AS model_id,
               c.created_at,
               c.updated_at
          FROM conversations c
          JOIN users u
            ON u.id = c.user_id
          LEFT JOIN models m
            ON m.id = c.model_id
         WHERE u.external_id = %(user_id)s
           AND (%(pattern)s::text IS NULL OR c.title ILIKE %(pattern)s ESCAPE '\\')
         ORDER BY c.updated_at DESC,
                  c.id DESC
         LIMIT %(limit)s
        OFFSET %(offset)s
    """

    params: dict[str, Any] = {
        "user_id": user_id,
        "pattern": pattern,
        "limit": per_page,
        "offset": (page - 1) * per_page,
    }

    async with conn.cursor() as cur:
        await cur.execute(count_sql, count_params)
        counted = await cur.fetchone()

        await cur.execute(sql, params)
        rows = await cur.fetchall()

    assert counted is not None  # count(*) always returns its one row

    total = counted["total"]
    pages = math.ceil(total / per_page)

    data = []
    for row in rows:
        conversation = to_conversation(row, running)
        data.append(conversation)

    meta = PageMeta(page=page, per_page=per_page, total=total, pages=pages)

    return ConversationPage(data=data, meta=meta)
