"""Arithmetic for fixed-window rate-limit keys and retry times."""

from __future__ import annotations

import hashlib
import math
from datetime import timedelta

__all__ = [
    "fixed_window_key",
    "fixed_window_retry_after",
    "fixed_window_seconds",
]


def fixed_window_seconds(window: timedelta) -> int:
    """Return *window* in whole seconds, rounded up and at least one."""
    return max(1, math.ceil(window.total_seconds()))


def fixed_window_key(scope: str, subject: str, window_seconds: int, now: float) -> str:
    """Return the scope-subject digest and bucket for *now* in epoch seconds."""
    digest = hashlib.sha256(f"{scope}\0{subject}".encode()).hexdigest()
    return f"{digest}:{int(now // window_seconds)}"


def fixed_window_retry_after(window_seconds: int, now: float) -> int:
    """Return whole seconds until the current window ends, for epoch *now*."""
    ends = (int(now // window_seconds) + 1) * window_seconds
    return max(1, math.ceil(ends - now))
