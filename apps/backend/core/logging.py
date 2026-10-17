"""Log formatting that keeps personal data out of exception text.

psycopg's error message is libpq's full text, so a CHECK violation carries
`DETAIL: Failing row contains (…name, email, mobile…)`, and `django.request` logs every 500 with
its traceback. This formatter keeps the stack frames but replaces the exception's text with its
class name and SQLSTATE. It reads no settings or env, so it imports with an empty environment.
"""

import logging
import traceback


def _class_name(exc: BaseException) -> str:
    cls = type(exc)
    if cls.__module__ == "builtins":
        return cls.__qualname__
    return f"{cls.__module__}.{cls.__qualname__}"


def _sqlstate(exc: BaseException) -> str | None:
    for candidate in (exc, exc.__cause__):
        sqlstate = getattr(candidate, "sqlstate", None)
        if sqlstate:
            return str(sqlstate)
    return None


class RedactingFormatter(logging.Formatter):
    def formatException(self, ei):
        _, exc, tb = ei
        lines = ["Traceback (most recent call last):\n", *traceback.format_tb(tb)]
        if exc is None:
            return "".join(lines).rstrip("\n")
        summary = _class_name(exc)
        if sqlstate := _sqlstate(exc):
            summary += f" sqlstate={sqlstate}"
        lines.append(summary)
        return "".join(lines)

    def format(self, record):
        # logging caches the formatted exception on the record. Ignore a cache written by another
        # handler's formatter, which may hold the unredacted text, and leave it as we found it.
        cached = record.exc_text
        record.exc_text = None
        try:
            return super().format(record)
        finally:
            record.exc_text = cached
