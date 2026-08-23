# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libpq for psycopg; build tools are dropped again in the same layer.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt \
    && apt-get purge -y --auto-remove build-essential

COPY . .

# Never run as root.
RUN useradd --system --create-home --uid 10001 dayflow \
    && mkdir -p /app/staticfiles \
    && chown -R dayflow:dayflow /app
USER dayflow

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/billing/plans/ || exit 1

# Daphne, not gunicorn: the app serves WebSockets as well as HTTP.
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "core.asgi:application"]
