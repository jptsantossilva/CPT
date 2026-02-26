#!/bin/sh
set -eu

if [ -f /app/alembic.ini ]; then
  echo "Running alembic migrations..."
  alembic upgrade head
fi

echo "Ensuring DB schema exists..."
python -c "from backend.app.db import init_db; init_db()"

echo "Starting FastAPI..."
exec uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
