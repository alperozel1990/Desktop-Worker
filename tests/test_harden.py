"""Tests for Phase 7 hardening: app allow/deny, profiles, config persistence."""

import pytest

from desktop_worker.config import Config
from desktop_worker.safety import build_policy
from desktop_worker.safety.policy import PermissionPolicy, RiskLevel, deny_all
from desktop_worker.tools.builtin import OpenAppTool
from desktop_worker.tools.registry import ToolError


# --- authorize_app --------------------------------------------------------

def test_authorize_app_no_lists_allows_all():
    p = PermissionPolicy()
    assert p.authorize_app("chrome")


def test_authorize_app_denylist_wins():
    p = PermissionPolicy(app_denylist=frozenset({"chrome"}))
    assert not p.authorize_app("Chrome")  # case-insensitive
    assert p.authorize_app("notepad")


def test_authorize_app_allowlist_restricts():
    p = PermissionPolicy(app_allowlist=frozenset({"notepad"}))
    assert p.authorize_app("notepad")
    assert not p.authorize_app("calc")


def test_authorize_app_deny_overrides_allow():
    p = PermissionPolicy(app_allowlist=frozenset({"chrome"}),
                         app_denylist=frozenset({"chrome"}))
    assert not p.authorize_app("chrome")


# --- build_policy with lists ----------------------------------------------

def test_build_policy_threads_app_lists():
    p = build_policy("standard", deny_all, app_allowlist=["notepad"],
                     app_denylist=["chrome"])
    assert p.app_allowlist == frozenset({"notepad"})
    assert p.app_denylist == frozenset({"chrome"})
    assert p.approval_threshold == RiskLevel.HIGH


def test_build_policy_unknown_profile_raises():
    with pytest.raises(ValueError):
        build_policy("bogus", deny_all)


# --- Config persistence ---------------------------------------------------

def test_config_has_profile_and_app_lists_defaults():
    c = Config()
    assert c.profile == "standard"
    assert c.app_allowlist == () and c.app_denylist == ()


def test_config_from_env_reads_lists(monkeypatch):
    monkeypatch.setenv("DW_PROFILE", "strict")
    monkeypatch.setenv("DW_APP_ALLOWLIST", "notepad, calc")
    monkeypatch.setenv("DW_APP_DENYLIST", "chrome")
    c = Config.from_env()
    assert c.profile == "strict"
    assert c.app_allowlist == ("notepad", "calc")
    assert c.app_denylist == ("chrome",)


# --- OpenAppTool enforces the policy --------------------------------------

class _FakeBroker:
    def __init__(self):
        self.commands = []

    def launch(self, command, cwd, **kw):
        self.commands.append(command)
        class R:
            blocked = False
            blockedReason = ""
        return R()


def test_open_app_denied_by_policy_does_not_launch():
    broker = _FakeBroker()
    policy = PermissionPolicy(app_denylist=frozenset({"chrome"}))
    tool = OpenAppTool(desktop_dir=".", broker=broker, policy=policy)
    out = tool.run({"app": "chrome"})
    assert not out["success"]
    assert "denied by permission policy" in out["error"]
    assert broker.commands == []  # never launched


def test_open_app_allowed_by_policy_launches():
    broker = _FakeBroker()
    policy = PermissionPolicy(app_allowlist=frozenset({"notepad"}))
    tool = OpenAppTool(desktop_dir=".", broker=broker, policy=policy)
    out = tool.run({"app": "notepad"})
    assert out["success"]
    assert broker.commands  # launched


def test_open_app_still_rejects_unknown_app_with_policy():
    tool = OpenAppTool(desktop_dir=".", broker=_FakeBroker(), policy=PermissionPolicy())
    with pytest.raises(ToolError):
        tool.run({"app": "powershell"})  # not in curated allowlist
