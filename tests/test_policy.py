from desktop_worker.safety.policy import (
    ApprovalRequest,
    PermissionPolicy,
    RiskLevel,
    auto_approve,
    deny_all,
)
from desktop_worker.schema.actions import parse_action


def test_low_risk_action_auto_allowed_even_with_deny_all():
    policy = PermissionPolicy(approval_callback=deny_all)
    action = parse_action({"type": "mouse.move", "x": 1, "y": 1})
    ok, risk = policy.authorize_action(action)
    assert ok is True
    assert risk == RiskLevel.LOW


def test_high_risk_blocked_by_deny_all():
    policy = PermissionPolicy(approval_callback=deny_all)
    req = ApprovalRequest(kind="cli", summary="del x", risk=RiskLevel.HIGH)
    assert policy.authorize(req) is False


def test_high_risk_allowed_by_auto_approve():
    policy = PermissionPolicy(approval_callback=auto_approve)
    req = ApprovalRequest(kind="cli", summary="del x", risk=RiskLevel.HIGH)
    assert policy.authorize(req) is True


def test_threshold_respected():
    policy = PermissionPolicy(approval_callback=deny_all, approval_threshold=RiskLevel.MEDIUM)
    # medium now requires approval -> denied
    assert policy.authorize(ApprovalRequest("cli", "npm install", RiskLevel.MEDIUM)) is False
    # low still auto-allowed
    assert policy.authorize(ApprovalRequest("action", "move", RiskLevel.LOW)) is True


def test_risk_ordering():
    assert RiskLevel.HIGH.at_least(RiskLevel.LOW)
    assert RiskLevel.MEDIUM.at_least(RiskLevel.MEDIUM)
    assert not RiskLevel.LOW.at_least(RiskLevel.HIGH)
