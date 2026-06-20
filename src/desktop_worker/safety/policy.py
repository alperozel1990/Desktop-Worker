"""Permission + risk policy (requirements sections 8, 11, 12).

The policy decides whether a structured action or CLI command may run, and
whether it requires explicit user approval. Approval is delivered through a
pluggable callback so the same policy works headless (deny-by-default),
in tests (auto-approve), or behind a real UI prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from desktop_worker.schema.actions import Action


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    def at_least(self, other: "RiskLevel") -> bool:
        order = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}
        return order[self] >= order[other]


@dataclass
class ApprovalRequest:
    """Context handed to the approval callback for a human decision."""

    kind: str                 # "action" | "cli"
    summary: str              # human readable description of what will run
    risk: RiskLevel
    detail: dict[str, Any] = field(default_factory=dict)


# An approval callback returns True to allow, False to deny.
ApprovalCallback = Callable[[ApprovalRequest], bool]


def deny_all(_req: ApprovalRequest) -> bool:
    """Default headless behavior: never approve high-risk operations."""
    return False


def auto_approve(_req: ApprovalRequest) -> bool:
    """Test/automation helper: approve everything. Never use in production."""
    return True


# Action types that are inherently elevated-risk and require approval.
_HIGH_RISK_ACTION_TYPES = frozenset({
    # File deletion / destructive fs actions will live here as fs.* lands.
})
_MEDIUM_RISK_ACTION_TYPES = frozenset({
    "window.focus",  # changes focus / app state
})


@dataclass
class PermissionPolicy:
    """Central gate for action and CLI approval."""

    approval_callback: ApprovalCallback = deny_all
    # Approve at or above this risk level requires the callback to say yes.
    approval_threshold: RiskLevel = RiskLevel.HIGH
    # Application allow/deny lists (Phase 7 — empty = no restriction yet).
    app_allowlist: frozenset[str] = frozenset()
    app_denylist: frozenset[str] = frozenset()

    def classify_action(self, action: Action) -> RiskLevel:
        if action.type in _HIGH_RISK_ACTION_TYPES:
            return RiskLevel.HIGH
        if action.type in _MEDIUM_RISK_ACTION_TYPES:
            return RiskLevel.MEDIUM
        # cli.run risk is classified by the broker's command classifier, not here.
        return RiskLevel.LOW

    def requires_approval(self, risk: RiskLevel) -> bool:
        return risk.at_least(self.approval_threshold)

    def authorize(self, request: ApprovalRequest) -> bool:
        """Return True if the operation may proceed.

        Operations below the approval threshold are auto-allowed. At/above the
        threshold, the approval callback decides. Deny-by-default headless.
        """
        if not self.requires_approval(request.risk):
            return True
        return bool(self.approval_callback(request))

    def authorize_action(self, action: Action) -> tuple[bool, RiskLevel]:
        risk = self.classify_action(action)
        ok = self.authorize(ApprovalRequest(
            kind="action", summary=str(action), risk=risk,
            detail=action.to_dict(),
        ))
        return ok, risk
