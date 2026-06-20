"""Structured action / observation / result schema (no side effects)."""

from desktop_worker.schema.actions import (
    Action,
    ActionValidationError,
    KNOWN_ACTION_TYPES,
    parse_action,
)
from desktop_worker.schema.observations import (
    ActiveWindow,
    Cursor,
    Element,
    Observation,
    Screen,
)
from desktop_worker.schema.results import (
    ActionResult,
    CliResult,
    VerificationResult,
)

__all__ = [
    "Action",
    "ActionValidationError",
    "KNOWN_ACTION_TYPES",
    "parse_action",
    "ActiveWindow",
    "Cursor",
    "Element",
    "Observation",
    "Screen",
    "ActionResult",
    "CliResult",
    "VerificationResult",
]
