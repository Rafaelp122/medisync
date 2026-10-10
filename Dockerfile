# syntax=docker/dockerfile:1

# ==============================================================================
# STAGE 1: Base - O mínimo necessário para runtime
# ==============================================================================
FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ==============================================================================
# STAGE 2: Builder - Onde o uv é necessário para gerar o venv
# ==============================================================================
FROM base AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-install-project --no-dev

# ==============================================================================
# STAGE 3: Development - Ambiente de desenvolvimento local com hot-reload
# ==============================================================================
FROM builder AS development

RUN uv sync --frozen --no-install-project

COPY . .

EXPOSE 8000

CMD ["granian", "src.main:app", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ==============================================================================
# STAGE 4: Production - Eficiência máxima para Cloud Run / Contêineres
# ==============================================================================
FROM base AS production

ENV PYTHONOPTIMIZE=1 \
    PYTHONNODEBUGRANGES=1

RUN useradd -m -u 1000 -s /bin/bash appuser

COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv

COPY --chown=appuser:appuser . .

RUN python -m compileall -q .

USER appuser

EXPOSE 8080

CMD ["sh", "-c", "exec granian src.main:app --interface asgi --host 0.0.0.0 --port ${PORT:-8080} --workers ${GRANIAN_WORKERS:-2} --backlog 1024 --http auto --no-access-log --log-level info"]
