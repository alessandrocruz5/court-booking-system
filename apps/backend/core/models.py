from django.db import models


class RateLimit(models.Model):
    """One fixed-window counter per (scope, hashed identifier). See `core.ratelimit`.

    `key` holds `scope:` plus an HMAC of the identifier, never the raw IP or email (RA 10173).
    """

    key = models.CharField(max_length=120, primary_key=True)
    window_start = models.DateTimeField()
    count = models.PositiveIntegerField()

    class Meta:
        db_table = "core_ratelimit"

    def __str__(self) -> str:
        return self.key
