"""gunicorn settings for Cloud Run: `gunicorn -c config/gunicorn.conf.py config.wsgi`."""

import os

from config.env import validate_runtime_env

# Cloud Run sends traffic to $PORT on every interface of the container.
bind = f"0.0.0.0:{os.environ.get('PORT', '8080')}"  # noqa: S104
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
worker_class = "gthread"
threads = 4
timeout = 30
graceful_timeout = 10

# Method, path without the query string, status, bytes and seconds. No IP, query or user agent,
# which keeps personal data out of the logs.
accesslog = "-"
access_log_format = "%(m)s %(U)s %(s)s %(b)s %(L)s"
errorlog = "-"

# Cloud Run's front end is the only peer, so trust its X-Forwarded-* headers.
forwarded_allow_ips = "*"


def on_starting(server):
    """Refuse to start when a required key is missing, blank or too short."""
    validate_runtime_env()
