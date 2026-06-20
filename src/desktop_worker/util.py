"""Small shared helpers with no third-party dependencies."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    """ISO-8601 UTC timestamp, e.g. 2026-06-20T10:00:00.123456+00:00.

    Centralized so audit entries, observations and results share one clock
    and are trivially sortable.
    """
    return datetime.now(timezone.utc).isoformat()
