FROM python:3.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Build tools and client library for mysqlclient.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential pkg-config default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

# Static files are collected into the image and served by WhiteNoise.
RUN DJANGO_SECRET_KEY=build-only DJANGO_DEBUG=false python manage.py collectstatic --noinput

# Run as an unprivileged user. sent_emails is a volume and takes this ownership on first use.
RUN useradd --system --uid 1000 --home /app app \
    && mkdir -p sent_emails data_dictionary \
    && chown -R app:app sent_emails data_dictionary \
    && chmod +x docker/entrypoint.sh
USER app

EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", \
     "--access-logfile", "-"]
