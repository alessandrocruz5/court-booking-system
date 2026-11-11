# syntax=docker/dockerfile:1

# Django backend for Cloud Run (service cb-backend and job cb-nightly). Build context is apps/backend:
#   docker build -t cb-backend:local apps/backend
# The build reads no environment: settings import with an empty env, and gunicorn validates the
# runtime env when it starts. No ENTRYPOINT, so the job can run `python manage.py nightly`.

FROM python:3.15-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
# Dependencies only, from the lockfile, so this layer is reused until uv.lock changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-dev --no-install-project
COPY . .
# Settings import with an empty environment, so collectstatic needs no variables.
RUN DJANGO_SETTINGS_MODULE=config.settings /app/.venv/bin/python manage.py collectstatic --noinput

FROM python:3.15-slim AS runtime
WORKDIR /app
# A home directory, because gunicorn creates its control socket in ~/.gunicorn.
RUN groupadd --system app \
    && useradd --system --gid app --create-home --home-dir /home/app --shell /usr/sbin/nologin app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080
COPY --from=builder --chown=app:app /app /app
USER app
EXPOSE 8080
CMD ["gunicorn", "config.wsgi", "-c", "config/gunicorn.conf.py"]
