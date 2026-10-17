import logging
import sys

from core.logging import RedactingFormatter

PII = "Failing row contains (Juan, juan@example.com)"


class CheckViolation(Exception):
    sqlstate = "23514"


class WrappedIntegrityError(Exception):
    """Stands in for Django's IntegrityError, which copies psycopg's text and chains it."""


def _record(exc_info):
    return logging.LogRecord(
        name="django.request",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="Internal Server Error: %s",
        args=("/api/v1/bookings",),
        exc_info=exc_info,
    )


def _raise_check_violation():
    raise CheckViolation(f'new row violates check constraint "x"\nDETAIL:  {PII}')


def _formatter():
    return RedactingFormatter("%(levelname)s %(name)s %(message)s")


def test_exception_text_is_replaced_by_class_and_sqlstate():
    try:
        _raise_check_violation()
    except CheckViolation:
        output = _formatter().format(_record(sys.exc_info()))

    assert "CheckViolation" in output
    assert "sqlstate=23514" in output
    assert "_raise_check_violation" in output
    assert 'File "' in output
    assert "juan@example.com" not in output
    assert "Failing row" not in output
    assert output.startswith("ERROR django.request Internal Server Error: /api/v1/bookings")


def test_sqlstate_is_read_from_the_cause():
    try:
        try:
            _raise_check_violation()
        except CheckViolation as exc:
            raise WrappedIntegrityError(*exc.args) from exc
    except WrappedIntegrityError:
        output = _formatter().format(_record(sys.exc_info()))

    assert "WrappedIntegrityError sqlstate=23514" in output
    assert "juan@example.com" not in output
    assert "Failing row" not in output


def test_a_cached_unredacted_traceback_is_not_reused():
    try:
        _raise_check_violation()
    except CheckViolation:
        record = _record(sys.exc_info())

    logging.Formatter("%(message)s").format(record)
    assert "Failing row" in record.exc_text

    output = _formatter().format(record)

    assert "Failing row" not in output
    assert "sqlstate=23514" in output
