FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.11 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH

WORKDIR /srv

# Dependencies first: this layer is only rebuilt when the manifests change.
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-install-project

COPY api/alembic.ini ./
COPY api/alembic ./alembic
COPY api/app ./app
COPY api/tests ./tests
COPY api/eval ./eval

# The drift test compares the migrations against this file.
COPY schema.sql ./schema.sql

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
