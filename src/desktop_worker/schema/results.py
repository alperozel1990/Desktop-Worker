"""Structured result records (requirements sections 8, 11, 14)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ActionResult:
    """Outcome of executing a single structured action."""

    action_type: str
    success: bool
    startedAt: str
    endedAt: str
    error: Optional[str] = None
    detail: dict[str, Any] = field(default_factory=dict)
    retries: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "actionType": self.action_type,
            "success": self.success,
            "startedAt": self.startedAt,
            "endedAt": self.endedAt,
            "error": self.error,
            "detail": self.detail,
            "retries": self.retries,
        }


@dataclass
class CliResult:
    """Structured CLI broker execution result (requirements section 11)."""

    command: str
    cwd: str
    startedAt: str
    endedAt: str
    exitCode: Optional[int]
    stdoutRef: Optional[str]
    stderrRef: Optional[str]
    elevated: bool
    riskLevel: str
    approvedByUser: bool
    timedOut: bool = False
    blocked: bool = False          # broker refused to run (e.g. denied approval)
    blockedReason: Optional[str] = None
    # Inline tails for quick inspection without opening the artifact files.
    stdoutTail: str = ""
    stderrTail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "cwd": self.cwd,
            "startedAt": self.startedAt,
            "endedAt": self.endedAt,
            "exitCode": self.exitCode,
            "stdoutRef": self.stdoutRef,
            "stderrRef": self.stderrRef,
            "elevated": self.elevated,
            "riskLevel": self.riskLevel,
            "approvedByUser": self.approvedByUser,
            "timedOut": self.timedOut,
            "blocked": self.blocked,
            "blockedReason": self.blockedReason,
        }


@dataclass
class VerificationResult:
    """Outcome of a verification check (requirements section 14)."""

    passed: bool
    method: str
    expected: dict[str, Any] = field(default_factory=dict)
    observed: dict[str, Any] = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "method": self.method,
            "expected": self.expected,
            "observed": self.observed,
            "note": self.note,
        }
