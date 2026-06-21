"""Permission profiles (requirements §12) — selectable safety presets.

A profile is a named :class:`PermissionPolicy` configuration so the user can pick
how cautious the agent is, keeping them in control:

  standard  low/medium auto-run (watchable), HIGH-risk prompts the user.
  strict    only LOW auto-runs; MEDIUM and HIGH (tool calls, window focus, app
            launches, risky CLI) prompt for approval.
  headless  never prompt; anything needing approval is DENIED (unattended-safe).
"""

from __future__ import annotations

from desktop_worker.safety.policy import (
    ApprovalCallback,
    PermissionPolicy,
    RiskLevel,
    deny_all,
)

PROFILES = ("standard", "strict", "headless")


def build_policy(profile: str, approval_callback: ApprovalCallback) -> PermissionPolicy:
    """Build a :class:`PermissionPolicy` for the named profile.

    ``approval_callback`` is used by the interactive profiles (standard/strict);
    headless ignores it and denies everything above LOW.
    """
    profile = (profile or "standard").lower()
    if profile == "headless":
        return PermissionPolicy(approval_callback=deny_all,
                                approval_threshold=RiskLevel.HIGH)
    if profile == "strict":
        return PermissionPolicy(approval_callback=approval_callback,
                                approval_threshold=RiskLevel.MEDIUM)
    if profile == "standard":
        return PermissionPolicy(approval_callback=approval_callback,
                                approval_threshold=RiskLevel.HIGH)
    raise ValueError(f"unknown permission profile: {profile!r} (choose from {PROFILES})")
