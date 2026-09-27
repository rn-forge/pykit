"""Response headers marking an endpoint deprecated."""

from __future__ import annotations

from datetime import datetime
from email.utils import format_datetime

__all__ = ["deprecation_headers"]


def deprecation_headers(
    *,
    deprecated_at: datetime,
    sunset: datetime | None = None,
    link: str | None = None,
) -> dict[str, str]:
    """Return the headers marking a response's endpoint deprecated.

    RFC 9745's ``Deprecation`` field carries *deprecated_at* as a
    structured-field date (``@<epoch-seconds>``). RFC 8594's ``Sunset`` field
    carries *sunset* as an HTTP-date, when given. *link* is emitted as
    ``Link: <link>; rel="deprecation"``, RFC 9745's link relation.

    Args:
        deprecated_at: When the endpoint became deprecated.
        sunset: When the endpoint stops being served. Omitted when unscheduled.
        link: A URI for the deprecation notice.

    Returns:
        ``Deprecation``, and ``Sunset``/``Link`` when given.
    """
    headers = {"Deprecation": f"@{int(deprecated_at.timestamp())}"}
    if sunset is not None:
        headers["Sunset"] = format_datetime(sunset, usegmt=True)
    if link is not None:
        headers["Link"] = f'<{link}>; rel="deprecation"'
    return headers
