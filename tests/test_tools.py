"""Tests for AI-callable tools (brain + reliable hands)."""

import pytest

from desktop_worker.actions.backends import NullInputBackend
from desktop_worker.actions.executor import ActionExecutor
from desktop_worker.audit.log import AuditLog
from desktop_worker.safety.emergency_stop import EmergencyStop
from desktop_worker.safety.policy import PermissionPolicy, deny_all
from desktop_worker.schema.actions import ActionValidationError, parse_action
from desktop_worker.tools import ToolRegistry
from desktop_worker.tools.builtin import CreateTextFileTool, _sanitize_filename
from desktop_worker.tools.registry import ToolError


class FakeTool:
    def __init__(self, name="create_text_file", risk="medium", ok=True, records=None):
        self.name = name
        self.description = "test tool"
        self.args_help = "filename, content"
        self.risk = risk
        self._ok = ok
        self.calls = records if records is not None else []

    def run(self, args):
        self.calls.append(args)
        return {"success": self._ok, "path": "X", "error": None if self._ok else "boom"}


def _registry(tool):
    r = ToolRegistry()
    r.register(tool)
    return r


def _executor(tmp_path, tools=None, approve=False, estop=None):
    audit = AuditLog(tmp_path / "audit.jsonl")
    from desktop_worker.safety.policy import auto_approve
    policy = PermissionPolicy(approval_callback=auto_approve if approve else deny_all)
    return ActionExecutor(audit=audit, policy=policy, input_backend=NullInputBackend(),
                          estop=estop or EmergencyStop(), tools=tools), audit


# --- schema --------------------------------------------------------------

def test_tool_run_schema_validation():
    a = parse_action({"type": "tool.run", "tool": "create_text_file",
                      "args": {"filename": "x", "content": "y"}})
    assert a.params["tool"] == "create_text_file"
    with pytest.raises(ActionValidationError):
        parse_action({"type": "tool.run"})                       # missing tool
    with pytest.raises(ActionValidationError):
        parse_action({"type": "tool.run", "tool": "x", "args": "notdict"})


# --- registry ------------------------------------------------------------

def test_registry_unknown_tool_is_high_risk_and_raises():
    r = ToolRegistry()
    assert r.risk_of("nope") == "high"           # unknown => HIGH (deny by default)
    with pytest.raises(ToolError):
        r.run("nope", {})


def test_registry_runs_and_propagates_failure():
    r = _registry(FakeTool(ok=True))
    assert r.run("create_text_file", {"filename": "a"})["success"] is True
    r2 = _registry(FakeTool(ok=False))
    with pytest.raises(ToolError):
        r2.run("create_text_file", {})


# --- arg sanitization ----------------------------------------------------

def test_filename_sanitization_rejects_paths():
    assert _sanitize_filename("notes") == "notes"
    assert _sanitize_filename("notes.txt") == "notes"
    for bad in ["..\\x", "a/b", "c:\\evil", "x/../y", "a\\b"]:
        with pytest.raises(ToolError):
            _sanitize_filename(bad)


def test_create_text_file_tool_writes_and_verifies(tmp_path):
    tool = CreateTextFileTool(desktop_dir=str(tmp_path), broker=None)  # no open
    res = tool.run({"filename": "demo", "content": "tool worked"})
    assert res["success"] is True
    f = tmp_path / "demo.txt"
    assert f.read_text(encoding="utf-8") == "tool worked"   # exact content, reliable


def test_create_text_file_tool_unicode_content(tmp_path):
    tool = CreateTextFileTool(desktop_dir=str(tmp_path), broker=None)
    tool.run({"filename": "tr", "content": "başlıyoruz"})
    assert (tmp_path / "tr.txt").read_text(encoding="utf-8") == "başlıyoruz"


def test_create_text_file_tool_rejects_bad_filename(tmp_path):
    tool = CreateTextFileTool(desktop_dir=str(tmp_path), broker=None)
    with pytest.raises(ToolError):
        tool.run({"filename": "../evil", "content": "x"})


# --- executor dispatch + gating -----------------------------------------

def test_executor_runs_tool_via_registry(tmp_path):
    tool = FakeTool()
    ex, audit = _executor(tmp_path, tools=_registry(tool))
    res = ex.execute(parse_action({"type": "tool.run", "tool": "create_text_file",
                                   "args": {"filename": "f", "content": "hi"}}))
    assert res.success
    assert tool.calls == [{"filename": "f", "content": "hi"}]
    assert "action.executed" in [e["event"] for e in audit.read_all()]


def test_executor_unknown_tool_fails_safe(tmp_path):
    ex, _ = _executor(tmp_path, tools=ToolRegistry(), approve=True)
    res = ex.execute(parse_action({"type": "tool.run", "tool": "ghost"}))
    assert res.success is False                    # unknown tool => action fails


def test_executor_failed_tool_fails_safe(tmp_path):
    ex, _ = _executor(tmp_path, tools=_registry(FakeTool(ok=False)))
    res = ex.execute(parse_action({"type": "tool.run", "tool": "create_text_file"}))
    assert res.success is False


def test_tool_run_without_registry_fails(tmp_path):
    # Even if approved, no registry => fails safe with a clear error.
    ex, _ = _executor(tmp_path, tools=None, approve=True)
    res = ex.execute(parse_action({"type": "tool.run", "tool": "create_text_file"}))
    assert res.success is False
    assert "registry" in (res.error or "")


def test_tool_run_without_registry_denied_by_default(tmp_path):
    # No registry + deny-by-default => treated as HIGH and blocked before dispatch.
    ex, _ = _executor(tmp_path, tools=None)
    res = ex.execute(parse_action({"type": "tool.run", "tool": "create_text_file"}))
    assert res.success is False


def test_medium_tool_auto_runs_high_tool_blocked(tmp_path):
    # deny_all + threshold HIGH: medium tool auto-runs; unknown(HIGH) is blocked.
    ex, _ = _executor(tmp_path, tools=_registry(FakeTool(risk="medium")))
    assert ex.execute(parse_action({"type": "tool.run", "tool": "create_text_file"})).success
    ex2, _ = _executor(tmp_path, tools=ToolRegistry())   # unknown tool => HIGH
    blocked = ex2.execute(parse_action({"type": "tool.run", "tool": "ghost"}))
    assert blocked.success is False


def test_estop_blocks_tool(tmp_path):
    es = EmergencyStop(); es.stop("halt")
    ex, _ = _executor(tmp_path, tools=_registry(FakeTool()), estop=es)
    res = ex.execute(parse_action({"type": "tool.run", "tool": "create_text_file"}))
    assert res.success is False
