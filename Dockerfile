# syntax=docker/dockerfile:1

# ── Stage 1: build the React frontend (web/dist) ─────────────────────────
FROM node:22-bookworm-slim AS web-build
WORKDIR /web

# Install deps against the lockfile first so this layer caches independently
# of source changes.
COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/ ./
RUN npm run build   # tsc -b && vite build -> /web/dist


# ── Stage 2: Python runtime serving the API + the built frontend ─────────
FROM python:3.12-slim-bookworm AS runtime

# uv, pinned. Copied from its published image rather than curl|sh.
COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /uvx /usr/local/bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_PYTHON=/usr/local/bin/python3 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PORT=8000

WORKDIR /app

# Resolve the dependency layer from just the lockfile so it caches across
# source edits. The project itself has no build-system and is run from
# source, so only its dependencies are installed.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Application code + the frontend bundle from stage 1. api/main.py mounts
# web/dist at "/" when it exists.
COPY core/ ./core/
COPY api/ ./api/
COPY --from=web-build /web/dist ./web/dist

# Drop privileges.
RUN useradd --system --uid 1000 app && chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,os,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/api/config').status==200 else 1)"

# Shell form so $PORT is expanded; uvicorn is exec'd via `sh -c`.
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
