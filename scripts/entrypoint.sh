#!/bin/sh
set -eu

assessorai-data migrate --migrations /app/migrations
exec uvicorn assessorai_dados.api:app --host 0.0.0.0 --port "${PORT:-8000}"
