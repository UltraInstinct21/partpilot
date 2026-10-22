"""Helpers for the query and path parameters.

Some endpoints of the frozen contract document no ``422`` response. A value
that cannot be parsed must therefore not raise a validation error - it is
clamped (query parameters) or answered with a ``404`` (path parameters).
"""

from __future__ import annotations


def clamp_int(value: object, default: int, minimum: int, maximum: int) -> int:
    """Parse an integer and clamp it into ``[minimum, maximum]``.

    A value that is not an integer falls back to ``default``.
    """
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def parse_int(value: object) -> int | None:
    """Parse an integer or return ``None`` when the value is not one."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


__all__ = ["clamp_int", "parse_int"]
