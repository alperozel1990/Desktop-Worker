"""Desktop observation layer."""

from desktop_worker.observation.backends import (
    DesktopBackend,
    NullDesktopBackend,
    get_desktop_backend,
)
from desktop_worker.observation.observer import Observer

__all__ = [
    "DesktopBackend",
    "NullDesktopBackend",
    "get_desktop_backend",
    "Observer",
]
