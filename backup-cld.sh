#!/bin/bash
# Back up the DCLD study database (mysqldump, gzip) and the code version.
# Usage: ./backup-cld.sh [label]      e.g. ./backup-cld.sh daily
# Prints the path of the database backup on the last line.
set -euo pipefail
cd "$(dirname "$0")"

BACKUP_DIR="${BACKUP_DIR:-$HOME/backups/cld-study}"
KEEP_DAYS="${KEEP_DAYS:-30}"
LABEL="${1:-manual}"
STAMP="$(date +%Y-%m-%d_%H%M%S)_${LABEL}"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

DB_FILE="$BACKUP_DIR/${STAMP}_db.sql.gz"
docker compose exec -T cld-db sh -c \
    'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -u root --single-transaction --routines --triggers --no-tablespaces "$MYSQL_DATABASE"' \
    | gzip > "$DB_FILE"
if [ ! -s "$DB_FILE" ] || ! gzip -t "$DB_FILE"; then
    echo "Backup failed: $DB_FILE is empty or damaged." >&2
    exit 1
fi
chmod 600 "$DB_FILE"
git rev-parse HEAD > "$BACKUP_DIR/${STAMP}_commit.txt" 2>/dev/null || true

find "$BACKUP_DIR" -name '*_db.sql.gz' -mtime +"$KEEP_DAYS" -delete
find "$BACKUP_DIR" -name '*_commit.txt' -mtime +"$KEEP_DAYS" -delete

echo "$DB_FILE"
