"""Tests for permission profiles (requirements §12)."""

import pytest

from desktop_worker.safety import build_policy
from desktop_worker.safety.policy import ApprovalRequest, RiskLevel, auto_approve


def _req(risk):
    return ApprovalRequest(kind="action", summary="x", risk=risk)


def test_standard_auto_runs_low_medium_prompts_high():
    p = build_policy("standard", auto_approve)
    assert p.authorize(_req(RiskLevel.LOW)) is True       # auto
    assert p.authorize(_req(RiskLevel.MEDIUM)) is True     # auto
    # HIGH consults the callback (here auto_approve => True; deny would block)
    assert p.requires_approval(RiskLevel.HIGH) is True
    assert p.requires_approval(RiskLevel.MEDIUM) is False


def test_strict_prompts_medium_and_high():
    p = build_policy("strict", auto_approve)
    assert p.authorize(_req(RiskLevel.LOW)) is True        # only low auto
    assert p.requires_approval(RiskLevel.MEDIUM) is True    # medium now prompts
    assert p.requires_approval(RiskLevel.HIGH) is True


def test_strict_denies_medium_when_callback_denies():
    deny = lambda req: False
    p = build_policy("strict", deny)
    assert p.authorize(_req(RiskLevel.MEDIUM)) is False     # denied (would prompt)
    assert p.authorize(_req(RiskLevel.LOW)) is True


def test_headless_denies_anything_needing_approval():
    # headless ignores the callback and denies >= HIGH; low/medium still auto.
    p = build_policy("headless", auto_approve)
    assert p.authorize(_req(RiskLevel.LOW)) is True
    assert p.authorize(_req(RiskLevel.MEDIUM)) is True
    assert p.authorize(_req(RiskLevel.HIGH)) is False       # denied despite auto_approve


def test_unknown_profile_raises():
    with pytest.raises(ValueError):
        build_policy("bogus", auto_approve)
