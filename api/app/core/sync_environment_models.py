"""Making the models table say what .env says, on every startup.

A model declared in .env is upserted by its env_name, so it keeps one id across
restarts and the conversations pointing at it keep their model. A model taken
out of .env is deleted; its conversations lose their model (ON DELETE SET NULL)
and ask for another at their next message.
"""

from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection

from app.domain.model_configs import EnvironmentModel


async def sync_environment_models(
    conn: AsyncConnection[Any],
    models: list[EnvironmentModel],
) -> None:
    upsert_sql = """
        INSERT INTO models AS m (env_name, name, adapter, base_url, model, dialect)
        VALUES (%(env_name)s, %(name)s, %(adapter)s, %(base_url)s, %(model)s, %(dialect)s)
            ON CONFLICT (env_name) DO UPDATE
           SET name = EXCLUDED.name,
               adapter = EXCLUDED.adapter,
               base_url = EXCLUDED.base_url,
               model = EXCLUDED.model,
               dialect = EXCLUDED.dialect
    """

    # The key is not in the row, by design and by constraint.
    delete_sql = """
        DELETE FROM models m
         WHERE m.env_name IS NOT NULL
           AND NOT (m.env_name = ANY (%(kept)s::text[]))
    """

    kept = []

    async with conn.transaction():
        for model in models:
            upsert_params: dict[str, Any] = {
                "env_name": model.env_name,
                "name": model.name,
                "adapter": model.adapter,
                "base_url": model.base_url,
                "model": model.model,
                "dialect": model.dialect,
            }
            await conn.execute(upsert_sql, upsert_params)
            kept.append(model.env_name)

        delete_params = {"kept": kept}
        await conn.execute(delete_sql, delete_params)
