"""Shared pytest fixtures for the backend.

pytest-django reads DJANGO_SETTINGS_MODULE (`config.settings_test`) from pyproject.toml. Tests
that touch the database need the Postgres from `compose.yaml` (`docker compose up -d --wait db`).
"""
