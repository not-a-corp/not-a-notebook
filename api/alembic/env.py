"""Alembic environment.

There is no metadata to autogenerate from: the project is raw SQL, so every
revision is written by hand with schema.sql as the target. The drift test is
what proves the two agree.

The URL comes from DATABASE_URL, with the driver named explicitly so SQLAlchemy
does not reach for psycopg2.
"""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import engine_from_config, pool


def _url() -> str:
    url = os.environ["DATABASE_URL"]
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def run_migrations_offline() -> None:
    context.configure(url=_url(), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    config = context.config
    config.set_main_option("sqlalchemy.url", _url())
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
