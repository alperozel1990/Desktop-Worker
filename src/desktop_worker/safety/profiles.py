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


def build_policy(profile: str, approval_callback: ApprovalCallback, *,
                 app_allowlist=frozenset(), app_denylist=frozenset()) -> PermissionPolicy:
    """Build a :class:`PermissionPolicy` for the named profile.

    ``approval_callback`` is used by the interactive profiles (standard/strict);
    headless ignores it and denies everything above LOW. ``app_allowlist`` /
    ``app_denylist`` further restrict which apps may be launched (Phase 7).
    """
    profile = (profile or "standard").lower()
    allow = frozenset(app_allowlist)
    deny = frozenset(app_denylist)
    if profile == "headless":
        return PermissionPolicy(approval_callback=deny_all,
                                approval_threshold=RiskLevel.HIGH,
                                app_allowlist=allow, app_denylist=deny)
    if profile == "strict":
        return PermissionPolicy(approval_callback=approval_callback,
                                approval_threshold=RiskLevel.MEDIUM,
                                app_allowlist=allow, app_denylist=deny)
    if profile == "standard":
        return PermissionPolicy(approval_callback=approval_callback,
                                approval_threshold=RiskLevel.HIGH,
                                app_allowlist=allow, app_denylist=deny)
    raise ValueError(f"unknown permission profile: {profile!r} (choose from {PROFILES})")
