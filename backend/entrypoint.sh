#!/usr/bin/env bash
set -e

echo "Waiting for PostgreSQL at ${POSTGRES_HOST:-postgres}:${POSTGRES_PORT:-5432}..."
until python -c "
import socket, os, sys
s = socket.socket()
s.settimeout(2)
try:
    s.connect((os.environ.get('POSTGRES_HOST','postgres'), int(os.environ.get('POSTGRES_PORT','5432'))))
    s.close()
except Exception:
    sys.exit(1)
"; do
  echo "  ...postgres not ready, retrying"
  sleep 2
done

echo "Running database migrations..."
alembic upgrade head || {
  echo "No migrations yet or upgrade failed; attempting autogenerate on first boot is disabled. Continuing."
}

echo "Starting: $*"
exec "$@"
