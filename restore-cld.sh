#!/bin/bash
# Restore a database backup made by backup-cld.sh.
# Usage: ./restore-cld.sh                 (lists backups, newest first, and asks which)
#        ./restore-cld.sh latest
#        ./restore-cld.sh /path/to/file_db.sql.gz
# Backs up the current state first (label before_restore), so a restore can be undone.
set -euo pipefail
cd "$(dirname "$0")"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups/cld-study}"

mapfile -t FILES < <(ls -1t "$BACKUP_DIR"/*_db.sql.gz 2>/dev/null | grep -v before_restore || true)
if [ "${#FILES[@]}" -eq 0 ]; then echo "No backups in $BACKUP_DIR" >&2; exit 1; fi

CHOICE="${1:-}"
if [ -z "$CHOICE" ]; then
    for i in "${!FILES[@]}"; do echo "$((i + 1))) $(basename "${FILES[$i]}")"; done
    read -rp "Backup to restore [1 = latest]: " N
    FILE="${FILES[$(( ${N:-1} - 1 ))]}"
elif [ "$CHOICE" = "latest" ]; then
    FILE="${FILES[0]}"
else
    FILE="$CHOICE"
fi
[ -f "$FILE" ] || { echo "Not found: $FILE" >&2; exit 1; }

echo "This REPLACES the current database with: $(basename "$FILE")"
read -rp "Type yes to continue: " OK
[ "$OK" = "yes" ] || { echo "Cancelled."; exit 1; }

SAFETY="$(./backup-cld.sh before_restore | tail -n1)"
echo "Current state saved to $SAFETY"

docker compose stop cld-web
gunzip -c "$FILE" | docker compose exec -T cld-db sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -u root "$MYSQL_DATABASE"'
docker compose run --rm cld-web python manage.py migrate --noinput
docker compose up -d cld-web

echo "Restored. To undo: ./restore-cld.sh $SAFETY"
