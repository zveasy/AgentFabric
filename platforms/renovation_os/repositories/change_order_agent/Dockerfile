FROM python:3.12-slim
WORKDIR /app
RUN useradd --create-home app
COPY . .
RUN pip install --no-cache-dir .
USER app
CMD ["uvicorn", "change_order_agent.api:app", "--host", "0.0.0.0", "--port", "8000"]
