"""Action layer: input backends + structured action executor."""

from desktop_worker.actions.backends import (
    InputBackend,
    NullInputBackend,
    get_input_backend,
)
from desktop_worker.actions.executor import ActionExecutor

__all__ = [
    "InputBackend",
    "NullInputBackend",
    "get_input_backend",
    "ActionExecutor",
]
