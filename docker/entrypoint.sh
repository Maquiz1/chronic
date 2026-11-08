#!/bin/sh
# Wait for MySQL, then run the container's command (gunicorn by default).
# Migrations are run by deploy-cld.sh, once, before the container switches to new code.
set -e

python - <<'PY'
import os, socket, sys, time
host, port = os.environ.get('DB_HOST', 'cld-db'), int(os.environ.get('DB_PORT', '3306'))
for _ in range(90):
    try:
        socket.create_connection((host, port), timeout=2).close()
        sys.exit(0)
    except OSError:
        time.sleep(1)
sys.exit(f'Database {host}:{port} is not reachable.')
PY

exec "$@"
