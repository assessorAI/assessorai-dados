FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY migrations ./migrations
COPY scripts/entrypoint.sh ./scripts/entrypoint.sh
RUN pip install --no-cache-dir .

CMD ["./scripts/entrypoint.sh"]
