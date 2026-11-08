#!/bin/bash
#
# Deploy the DCLD study system on the Hostinger server (/opt/chronic), same steps as ncd_penplus:
#   1. back up the database
#   2. build the new image while the old site keeps serving
#   3. migrate the database
#   4. switch the container to the new code
#
# Usage:  git pull && ./deploy-cld.sh
# First time: ./deploy-cld.sh --first   (also asks for the first Admin account)

set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
    echo "Missing .env. Run: cp .env.production.example .env  and fill in the values." >&2
    exit 1
fi

# 1. Backup ----------------------------------------------------------------------
if docker compose ps --status running --services 2>/dev/null | grep -qx cld-db; then
    DB_BACKUP="$(./backup-cld.sh before_deploy | tail -n1)"
else
    echo "Database container is not running yet (first deployment?): skipping backup."
    DB_BACKUP=""
fi

# 2. Build -----------------------------------------------------------------------
echo "Building the new image (the current site keeps running)..."
docker compose build cld-web  # cld-worker and cld-beat use the same image

# 3. Migrate ---------------------------------------------------------------------
echo "Starting the database and Redis if needed..."
docker compose up -d --wait cld-db cld-redis

echo "Migrations that will run:"
docker compose run --rm cld-web python manage.py migrate --plan
echo "Running database migrations..."
docker compose run --rm cld-web python manage.py migrate --noinput

# 4. Switch ----------------------------------------------------------------------
echo "Switching to the new code..."
docker compose up -d

echo "Creating scheduled tasks (existing schedules and on/off settings are kept)..."
docker compose exec -T cld-web python manage.py setup_schedules

echo "Checking that the data dictionary builds for this version..."
docker compose exec -T cld-web python manage.py build_dictionary --dir /tmp >/dev/null && echo "OK"

if [ "${1:-}" = "--first" ]; then
    echo "Create the first Admin account (log in with this email):"
    docker compose exec cld-web python manage.py createsuperuser
fi

echo
docker compose ps
echo
echo "Deployment completed. Check from the server:  curl -sI http://127.0.0.1:\${WEB_PORT:-8093}/accounts/login/"
if [ -n "$DB_BACKUP" ]; then
    echo "Backup from before this deployment: $DB_BACKUP"
    echo "To roll back the code:    git checkout \$(cat ${DB_BACKUP%_db.sql.gz}_commit.txt) && docker compose build cld-web  # cld-worker and cld-beat use the same image && docker compose up -d"
    echo "To restore the database:  ./restore-cld.sh $DB_BACKUP"
fi
