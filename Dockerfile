FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml README.md /app/
COPY agentfabric /app/agentfabric
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic

RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

EXPOSE 8000

RUN adduser --disabled-password --gecos "" --uid 10001 agentfabric
USER agentfabric

# Production: set AGENTFABRIC_DATABASE_URL, AGENTFABRIC_REDIS_URL, AGENTFABRIC_JWT_SECRET (and optionally
# AGENTFABRIC_ENVIRONMENT=production) via env or config. When unset, defaults allow local/dev runs.
CMD ["sh", "-c", "exec python -m agentfabric.cli api-run \
  --database-url \"${AGENTFABRIC_DATABASE_URL:-sqlite:///./agentfabric_api.db}\" \
  --redis-url \"${AGENTFABRIC_REDIS_URL:-redis://localhost:6379/0}\" \
  --jwt-secret \"${AGENTFABRIC_JWT_SECRET:-change-me-in-production}\" \
  --host 0.0.0.0 --port 8000"]
