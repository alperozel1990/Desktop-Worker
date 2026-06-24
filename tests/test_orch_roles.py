"""Tests for orchestration roles (Phase 6). Claude is stubbed via injected ask."""

import json

from desktop_worker.audit.log import AuditLog
from desktop_worker.orchestration import (
    AgentReport,
    AgentTask,
    CodexAuditor,
    Implementer,
    NorthstarAuditor,
    Strategist,
)
from desktop_worker.orchestration.claude_io import load_json


# --- load_json ------------------------------------------------------------

def test_load_json_direct_and_fenced():
    assert load_json('{"a": 1}') == {"a": 1}
    assert load_json("```json\n[1, 2]\n```") == [1, 2]


def test_load_json_embedded_in_prose():
    raw = 'Sure! Here is the plan:\n[{"id":"T1","goal":"g"}]\nHope that helps.'
    assert load_json(raw) == [{"id": "T1", "goal": "g"}]


def test_load_json_handles_many_braces_fast():
    # Adversarial-ish: many non-JSON '{' before a valid object must not hang.
    raw = "{" * 5000 + ' here {"ok": true}'
    assert load_json(raw) == {"ok": True}


def test_load_json_raises_when_absent():
    try:
        load_json("no json here")
        assert False
    except ValueError:
        pass


# --- Strategist -----------------------------------------------------------

def test_strategist_plans_tasks():
    arr = json.dumps([{"id": "T1", "goal": "open notepad", "acceptance": ["typed"]},
                      {"id": "T2", "goal": "save file"}])
    s = Strategist(ask=lambda p: arr)
    tasks = s.plan("write a note")
    assert [t.id for t in tasks] == ["T1", "T2"]
    assert tasks[0].acceptance == ["typed"]


def test_strategist_skips_bad_task_keeps_good():
    arr = json.dumps([{"id": "T1", "goal": "ok"}, {"goal": "no id"}])
    s = Strategist(ask=lambda p: arr)
    tasks = s.plan("x")
    assert [t.id for t in tasks] == ["T1"]


def test_strategist_fails_safe_on_non_array():
    s = Strategist(ask=lambda p: '{"not": "an array"}')
    assert s.plan("x") == []
    assert s.last_error


def test_strategist_fails_safe_on_garbage():
    s = Strategist(ask=lambda p: "the model rambled with no json")
    assert s.plan("x") == []


# --- Implementer ----------------------------------------------------------

def test_implementer_returns_report():
    rep = json.dumps({"taskId": "T1", "status": "done", "summary": "did it"})
    impl = Implementer(ask=lambda p: rep)
    r = impl.implement(AgentTask(id="T1", goal="g"))
    assert r.status == "done" and r.task_id == "T1"


def test_implementer_fails_safe_on_bad_output():
    impl = Implementer(ask=lambda p: "nope")
    r = impl.implement(AgentTask(id="T9", goal="g"))
    assert r.status == "failed" and r.task_id == "T9"


def test_implementer_uses_injected_execute_fn():
    def execute(task):
        return AgentReport(task_id=task.id, status="done", summary="executed live")
    impl = Implementer(execute_fn=execute)
    r = impl.implement(AgentTask(id="T1", goal="g"))
    assert r.summary == "executed live"


def test_implementer_execute_fn_error_is_safe():
    def execute(task):
        raise RuntimeError("boom")
    impl = Implementer(execute_fn=execute)
    r = impl.implement(AgentTask(id="T1", goal="g"))
    assert r.status == "failed"


# --- Auditors -------------------------------------------------------------

def test_codex_auditor_returns_finding():
    f = json.dumps({"severity": "low", "verdict": "approve", "message": "lgtm"})
    a = CodexAuditor(ask=lambda p: f)
    finding = a.review(AgentTask(id="T1", goal="g"),
                       AgentReport(task_id="T1", status="done"))
    assert finding.verdict == "approve"


def test_auditor_fails_closed_on_bad_output():
    a = NorthstarAuditor(ask=lambda p: "model said yes but no json")
    finding = a.review(AgentTask(id="T1", goal="g"),
                       AgentReport(task_id="T1", status="done"))
    assert finding.verdict == "block"  # deny-by-default
    assert finding.severity == "high"


def test_role_records_audit_events(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    arr = json.dumps([{"id": "T1", "goal": "g"}])
    Strategist(ask=lambda p: arr, audit=audit).plan("x")
    events = [e["event"] for e in audit.read_all()]
    assert "orch.planned" in events


def test_role_requires_ask_or_broker():
    try:
        Strategist()
        assert False
    except ValueError:
        pass
