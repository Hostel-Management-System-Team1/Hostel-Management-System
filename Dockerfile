# Production image for the Hostel Management System (HMS).
#
# The image runs only the Django application under gunicorn. TLS, static files and rate limiting
# belong to the reverse proxy in front of it (SAD 3.6, deploy/nginx.conf.example): copy
# /app/staticfiles out of the image for nginx to serve, and run with HMS_BEHIND_PROXY=true.
#
#   docker build -t hms .
#   docker run --rm -p 8000:8000 --env-file .env hms
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt requirements-prod.txt ./
RUN pip install -r requirements-prod.txt

COPY . .

# Gather the static files into /app/staticfiles. The key is only for this build step.
RUN DJANGO_SECRET_KEY=build-only-not-used-at-runtime DJANGO_DEBUG=false \
    python manage.py collectstatic --noinput

# Do not run as root.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin hms && chown -R hms /app
USER hms

EXPOSE 8000

# The process is healthy when something is listening on the port.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import socket; socket.create_connection(('127.0.0.1', 8000), 3).close()"

CMD ["gunicorn", "hms.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
