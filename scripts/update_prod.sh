#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
TS="$(date +%Y%m%d_%H%M%S)"

mkdir -p "${BACKUP_DIR}"

echo "[1/4] Creating Postgres backup..."
docker compose -f "${COMPOSE_FILE}" exec -T db \
  pg_dump -U "${POSTGRES_USER:-cpt}" -d "${POSTGRES_DB:-cpt}" \
  > "${BACKUP_DIR}/cpt_${TS}.sql"

echo "[2/4] Pulling/building images..."
docker compose -f "${COMPOSE_FILE}" pull

if [ "${BUILD_LOCAL:-0}" = "1" ]; then
  docker compose -f "${COMPOSE_FILE}" build
fi

echo "[3/4] Recreating containers..."
docker compose -f "${COMPOSE_FILE}" up -d

echo "[4/4] Done."
echo "Backup saved at ${BACKUP_DIR}/cpt_${TS}.sql"
