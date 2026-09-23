# syntax=docker/dockerfile:1
# MHVP API, worker, beat and migrate image. Build context: apps/api.

FROM ghcr.io/astral-sh/uv:0.8.17 AS uv

FROM python:3.12.11-slim-bookworm AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python:3.12.11-slim-bookworm AS runtime
ARG MHVP_APP_VERSION=0.1.0
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MHVP_APP_VERSION=${MHVP_APP_VERSION}
# Apply Debian security fixes (Trivy gate in CI).
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd --system --gid 10001 mhvp \
    && useradd --system --uid 10001 --gid mhvp --no-create-home --home-dir /app mhvp
WORKDIR /app
# The project is installed editable into the venv, so /app/src is the import location
# (compose.dev.yaml bind mounts it for --reload).
COPY --from=build /app/.venv /app/.venv
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
USER mhvp
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live', timeout=3).status == 200 else 1)"]
CMD ["uvicorn", "mhvp.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
# Trusted proxy addresses: set FORWARDED_ALLOW_IPS (uvicorn env) to the Traefik network, never "*".
