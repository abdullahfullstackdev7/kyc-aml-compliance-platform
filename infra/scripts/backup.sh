#!/bin/sh
# Nightly pg_dump with retention (PROJECT_PLAN.md Phase 11.2). Run from the
# `backup` service in infra/docker-compose.prod.yml, which mounts the same
# named volume this script writes to.
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
FILE="${BACKUP_DIR}/sentinelkyc-${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

echo "Backing up ${POSTGRES_DB} to ${FILE}"
pg_dump -h "${POSTGRES_HOST}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" | gzip > "${FILE}"

echo "Removing backups older than ${RETENTION_DAYS} days"
find "${BACKUP_DIR}" -name 'sentinelkyc-*.sql.gz' -mtime "+${RETENTION_DAYS}" -delete

echo "Backup complete: ${FILE} ($(du -h "${FILE}" | cut -f1))"
