# The image every conversation's kernel runs in. It is a product artefact,
# versioned like code: the container has no internet, so a package that is not
# baked in here does not exist for the generated code.

FROM python:3.14-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.9.11 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /src
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project


# uv stays behind in the build stage: nothing in the running image installs
# anything.
FROM python:3.14-slim

COPY --from=build /opt/venv /opt/venv

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    # fig.show() emits the figure as an application/vnd.plotly.v1+json display
    # message: the client renders the spec, in its own theme. No HTML, no PNG.
    PLOTLY_RENDERER=plotly_mimetype

# Generated code runs as a user with nothing to own but its home. /data is where
# the conversation's files are mounted, read-only.
RUN useradd --uid 1000 --create-home analyst \
 && mkdir /data /run/kernel

COPY check.py /opt/sandbox/check.py

USER analyst
WORKDIR /home/analyst

# The API writes the connection file — fixed ports, a fresh HMAC key per kernel
# — and mounts it here, so no message reaches the kernel unsigned.
CMD ["python", "-m", "ipykernel_launcher", "-f", "/run/kernel/connection.json"]
