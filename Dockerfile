# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# Multi-stage build: a small, non-root runtime image.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install build deps only in the builder layer.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY app ./app

# Build a wheel and install it (plus asyncpg for PostgreSQL) into a venv.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip && pip install . asyncpg

# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Create an unprivileged user.
RUN groupadd --system upgi && useradd --system --gid upgi --home /app upgi

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY app ./app
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

USER upgi

EXPOSE 8000

# Basic container healthcheck against the liveness probe.
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live').status==200 else 1)"

CMD ["python", "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
