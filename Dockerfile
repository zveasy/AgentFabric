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

CMD ["python", "-m", "agentfabric.cli", "api-run", "--database-url", "sqlite:///./agentfabric_api.db", "--host", "0.0.0.0", "--port", "8000"]
