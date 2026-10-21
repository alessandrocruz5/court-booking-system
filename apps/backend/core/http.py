"""The client's IP address, as a rate-limit key.

Assumption (verified in production by the runbook): every request reaches Django through Cloud
Run's front end, which appends the address it received the connection from to
`X-Forwarded-For`. So only the RIGHTMOST entry is trusted; anything to its left was sent by the
client and can be forged. Without the header (local development, tests) `REMOTE_ADDR` is used.

The key is normalised by `normalise_ip`, which `storefront.views` also uses for the IP the web
server forwards, so one client can't dodge a limit by varying its address: an IPv4-mapped IPv6
address counts as its IPv4 address, a plain IPv6 address as its /64 (one subscriber's usual
allocation), and a zone ID (`fe80::1%eth0`) is invalid.
An IP address is personal data (RA 10173): never log the result.
"""

import ipaddress

_UNKNOWN = "0.0.0.0"  # noqa: S104 (a rate-limit key, not a bind address)


def normalise_ip(value) -> str | None:
    """An IP address as a rate-limit key (IPv4, or an IPv6 address's /64), or None if invalid."""
    if not isinstance(value, str) or "%" in value:
        return None
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is None:
            return str(ipaddress.ip_network(f"{address}/64", strict=False))
        address = address.ipv4_mapped
    return str(address)


def client_ip(request) -> str:
    """The rate-limit key for the request's client: the rightmost `X-Forwarded-For` entry, else
    `REMOTE_ADDR`, else "0.0.0.0" (so every unidentifiable request shares one bucket)."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        key = normalise_ip(forwarded.rsplit(",", 1)[-1])
        if key is not None:
            return key
    return normalise_ip(request.META.get("REMOTE_ADDR")) or _UNKNOWN
