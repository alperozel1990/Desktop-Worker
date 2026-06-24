"""Handoff schema for multi-agent orchestration (requirements Phase 6).

Three immutable records pass between the roles:

* ``AgentTask``      a scoped unit of work the Strategist hands to an Implementer
                     (goal + acceptance criteria + constraints + forbidden files).
* ``AgentReport``    an Implementer's outcome for one task (status + evidence).
* ``AuditorFinding`` a Codex/Northstar verdict on a report.

Each has a hand-written camelCase ``to_dict()`` (the wire form) and a standalone
``parse_*`` validator that rejects unexpected fields and bad types — mirroring
``schema/actions.py`` so a malformed model response fails safe instead of
executing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class OrchestrationValidationError(ValueError):
    """Raised when an orchestration payload is malformed."""


# --- validation helpers (mirrors schema/actions.py style) -----------------

def _require_dict(data: Any, what: str) -> dict:
    if not isinstance(data, dict):
        raise OrchestrationValidationError(f"{what} must be an object, got {type(data).__name__}")
    return data


def _str(data: dict, key: str, *, required: bool = False, default: str = "") -> str:
    if key not in data:
        if required:
            raise OrchestrationValidationError(f"missing required field {key!r}")
        return default
    val = data[key]
    if not isinstance(val, str):
        raise OrchestrationValidationError(f"field {key!r} must be a string")
    return val


def _str_list(data: dict, key: str) -> list[str]:
    if key not in data:
        return []
    val = data[key]
    if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
        raise OrchestrationValidationError(f"field {key!r} must be a list of strings")
    return list(val)


def _reject_unexpected(data: dict, allowed: set[str], what: str) -> None:
    extra = set(data) - allowed
    if extra:
        raise OrchestrationValidationError(
            f"{what} has unexpected field(s): {', '.join(sorted(extra))}")


def _enum(value: str, allowed: tuple[str, ...], key: str) -> str:
    if value not in allowed:
        raise OrchestrationValidationError(
            f"field {key!r} must be one of {allowed}, got {value!r}")
    return value


# --- AgentTask ------------------------------------------------------------

_STATUSES = ("done", "blocked", "failed", "skipped")
_VERDICTS = ("approve", "revise", "block")
_SEVERITIES = ("info", "low", "medium", "high", "critical")


@dataclass(frozen=True)
class AgentTask:
    """A scoped unit of work handed from Strategist to Implementer."""

    id: str
    goal: str
    acceptance: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    forbidden_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "goal": self.goal, "acceptance": list(self.acceptance),
                "constraints": list(self.constraints),
                "forbiddenFiles": list(self.forbidden_files)}


def parse_agent_task(data: Any) -> AgentTask:
    data = _require_dict(data, "AgentTask")
    _reject_unexpected(data, {"id", "goal", "acceptance", "constraints", "forbiddenFiles"},
                       "AgentTask")
    return AgentTask(
        id=_str(data, "id", required=True),
        goal=_str(data, "goal", required=True),
        acceptance=_str_list(data, "acceptance"),
        constraints=_str_list(data, "constraints"),
        forbidden_files=_str_list(data, "forbiddenFiles"))


# --- AgentReport ----------------------------------------------------------

@dataclass(frozen=True)
class AgentReport:
    """An Implementer's outcome for one task."""

    task_id: str
    status: str  # one of _STATUSES
    summary: str = ""
    changes: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"taskId": self.task_id, "status": self.status, "summary": self.summary,
                "changes": list(self.changes), "evidence": list(self.evidence)}


def parse_agent_report(data: Any) -> AgentReport:
    data = _require_dict(data, "AgentReport")
    _reject_unexpected(data, {"taskId", "status", "summary", "changes", "evidence"},
                       "AgentReport")
    return AgentReport(
        task_id=_str(data, "taskId", required=True),
        status=_enum(_str(data, "status", required=True), _STATUSES, "status"),
        summary=_str(data, "summary"),
        changes=_str_list(data, "changes"),
        evidence=_str_list(data, "evidence"))


# --- AuditorFinding -------------------------------------------------------

@dataclass(frozen=True)
class AuditorFinding:
    """A Codex/Northstar verdict on an implementer report."""

    severity: str  # one of _SEVERITIES
    verdict: str   # one of _VERDICTS
    message: str = ""
    location: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"severity": self.severity, "verdict": self.verdict,
                "message": self.message, "location": self.location}


def parse_finding(data: Any) -> AuditorFinding:
    data = _require_dict(data, "AuditorFinding")
    _reject_unexpected(data, {"severity", "verdict", "message", "location"},
                       "AuditorFinding")
    return AuditorFinding(
        severity=_enum(_str(data, "severity", required=True), _SEVERITIES, "severity"),
        verdict=_enum(_str(data, "verdict", required=True), _VERDICTS, "verdict"),
        message=_str(data, "message"),
        location=_str(data, "location"))
