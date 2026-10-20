"""The runtime role `cb_app` (migration `core.0002_app_role`) gets DML only: no DDL and a
read-only `django_migrations`. The test user is a superuser, so tests switch with SET ROLE."""

from contextlib import contextmanager

import pytest
from django.db import DatabaseError, ProgrammingError, connection, transaction

pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)


@contextmanager
def as_cb_app():
    with connection.cursor() as cursor:
        cursor.execute("SET ROLE cb_app")
        try:
            yield cursor
        finally:
            cursor.execute("RESET ROLE")


def test_cb_app_role_exists_and_cannot_log_in():
    with connection.cursor() as cursor:
        cursor.execute("SELECT rolcanlogin, rolsuper FROM pg_roles WHERE rolname = 'cb_app'")
        assert cursor.fetchone() == (False, False)


def test_dml_on_app_tables_succeeds():
    with as_cb_app() as cursor:
        cursor.execute("SELECT count(*) FROM bookings_court")
        assert cursor.fetchone() == (18,)

        cursor.execute(
            "INSERT INTO bookings_court (code, name, kind, sort_order, is_active) "
            "VALUES ('zz-1', 'Throwaway', 'tennis', 999, false) RETURNING id"
        )
        (court_id,) = cursor.fetchone()
        cursor.execute("DELETE FROM bookings_court WHERE id = %s", [court_id])
        assert cursor.rowcount == 1

        cursor.execute(
            "INSERT INTO core_ratelimit (key, window_start, count) VALUES ('test:grant', now(), 1)"
        )
        cursor.execute("SELECT count FROM core_ratelimit WHERE key = 'test:grant'")
        assert cursor.fetchone() == (1,)
        cursor.execute("UPDATE core_ratelimit SET count = 2 WHERE key = 'test:grant'")
        assert cursor.rowcount == 1
        cursor.execute("DELETE FROM core_ratelimit WHERE key = 'test:grant'")
        assert cursor.rowcount == 1


def test_ddl_is_refused():
    with (
        as_cb_app() as cursor,
        pytest.raises(ProgrammingError, match="permission denied"),
        transaction.atomic(),
    ):
        cursor.execute("CREATE TABLE t_forbidden (id int)")


def test_django_migrations_is_read_only():
    with as_cb_app() as cursor:
        cursor.execute("SELECT count(*) FROM django_migrations")
        assert cursor.fetchone()[0] > 0

        with pytest.raises(DatabaseError, match="permission denied"), transaction.atomic():
            cursor.execute(
                "INSERT INTO django_migrations (app, name, applied) VALUES ('x', 'y', now())"
            )
        with pytest.raises(DatabaseError, match="permission denied"), transaction.atomic():
            cursor.execute("DELETE FROM django_migrations WHERE app = 'core'")
