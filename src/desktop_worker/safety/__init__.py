"""Safety layer: emergency stop, pause, permission/risk policy, limits."""

from desktop_worker.safety.emergency_stop import EmergencyStop, EmergencyStopError
from desktop_worker.safety.policy import (
    ApprovalRequest,
    PermissionPolicy,
    RiskLevel,
    deny_all,
    auto_approve,
)
from desktop_worker.safety.profiles import PROFILES, build_policy

__all__ = [
    "EmergencyStop",
    "EmergencyStopError",
    "ApprovalRequest",
    "PermissionPolicy",
    "RiskLevel",
    "deny_all",
    "auto_approve",
    "PROFILES",
    "build_policy",
]
