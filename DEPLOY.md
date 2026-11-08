# Deploying the DCLD study system (Hostinger, Docker + MySQL)

Same server and approach as ncd_penplus (`31.97.187.66`). Project folder `/opt/chronic`.

## How it fits on the server

- Address: **https://chronic.tamris.org**.
  The host nginx forwards it to `127.0.0.1:8093` (penplus uses 8090, dimension 8091, ODK Central 8092).
- Containers: `cld-db` (MySQL 8.4) and `cld-web` (gunicorn + WhiteNoise). Only `cld-web` has a port, and only on
  127.0.0.1, so nothing is reachable from outside except through nginx and HTTPS.
- Data lives in the Docker volume `chronic_mysql_data`.

## First deployment

```bash
ss -tlnp | grep ':8093 ' || echo "8093 is free"      # otherwise pick another WEB_PORT
cd /opt && git clone git@github.com:Maquiz1/chronic.git && cd chronic
cp .env.production.example .env
nano .env        # DJANGO_SECRET_KEY, DB_PASSWORD, DB_ROOT_PASSWORD (openssl rand -base64 48), domain, email password
chmod 600 .env
./deploy-cld.sh --first          # asks for the first Admin account at the end
```
Check from the server: `curl -sI http://127.0.0.1:8093/accounts/login/` (a `301` to HTTPS is normal).

## Domain and HTTPS

1. DNS: an A record for the domain → `31.97.187.66` (check with `dig +short chronic.tamris.org`).
2. As root:
   ```bash
   cp /opt/chronic/docker/nginx-cld.conf /etc/nginx/sites-available/chronic.tamris.org
   ln -s /etc/nginx/sites-available/chronic.tamris.org /etc/nginx/sites-enabled/
   nginx -t && systemctl reload nginx
   certbot --nginx -d chronic.tamris.org
   ```
3. Open the site and log in with the Admin account. Logins only work over HTTPS (secure cookies).

## Email must work

Registration confirmation, password reset and approval emails need SMTP. `.env.production.example` has the Hostinger
mailbox settings (same as tamris). After changing `.env`: `docker compose up -d cld-web`. Test:
```bash
docker compose exec cld-web python manage.py sendtestemail you@example.org
```

## Updates

```bash
cd /opt/chronic && git pull && ./deploy-cld.sh
```
It backs up the database to `~/backups/cld-study`, builds the new image while the old one keeps serving, runs
migrations and switches the container. It prints rollback and restore commands at the end.

## Backups

```bash
./backup-cld.sh                  # database + code version, kept 30 days (KEEP_DAYS)
./restore-cld.sh                 # lists backups and asks which; backs up the current state first
```
Daily backup (`crontab -e`):
```
15 2 * * * cd /opt/chronic && ./backup-cld.sh daily >> ~/backups/cld-study/backup.log 2>&1
```
Copy backups off the server regularly.

## Useful commands

```bash
docker compose ps
docker compose logs -f cld-web
docker compose exec cld-web python manage.py shell
docker compose exec cld-web python manage.py createsuperuser
docker compose exec cld-db sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -u root "$MYSQL_DATABASE"'
```

## Never in git

`.env`, database backups, `documentations/` (the lab screenshot shows a real patient's name and numbers) and `data_dictionary/` (send the workbook directly, or download it from Exports in the app).
