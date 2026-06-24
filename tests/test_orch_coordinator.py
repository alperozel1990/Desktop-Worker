"""Tests for the orchestration coordinator state machine (Phase 6)."""

import json

from desktop_worker.audit.log import AuditLog
from desktop_worker.orchestration import (
    AgentReport,
    AgentTask,
    AuditorFinding,
    CodexAuditor,
    Coordinator,
    Implementer,
    NorthstarAuditor,
    Strategist,
)


# --- stub roles for pure state-machine tests ------------------------------

class StubStrategist:
    def __init__(self, tasks, last_error=""):
        self._tasks = tasks
        self.last_error = last_error

    def plan(self, goal):
        return self._tasks


class StubImplementer:
    def __init__(self, status="done"):
        self._status = status

    def implement(self, task):
        return AgentReport(task_id=task.id, status=self._status, summary="s")


class StubAuditor:
    def __init__(self, verdict="approve", severity="low"):
        self._v = verdict
        self._s = severity

    def review(self, task, report):
        return AuditorFinding(severity=self._s, verdict=self._v)


def _coord(strategist, implementer, codex, northstar, audit=None):
    return Coordinator(strategist=strategist, implementer=implementer,
                       codex=codex, northstar=northstar, audit=audit)


def test_accepted_when_done_and_both_approve():
    c = _coord(StubStrategist([AgentTask(id="T1", goal="g")]),
               StubImplementer("done"), StubAuditor("approve"), StubAuditor("approve"))
    res = c.run("goal")
    assert res.accepted == 1 and res.blocked == 0
    assert res.outcomes[0].outcome == "accepted"


def test_blocked_when_any_auditor_blocks():
    c = _coord(StubStrategist([AgentTask(id="T1", goal="g")]),
               StubImplementer("done"), StubAuditor("approve"), StubAuditor("block"))
    res = c.run("goal")
    assert res.blocked == 1
    assert res.outcomes[0].outcome == "blocked"


def test_blocked_when_implementer_failed():
    c = _coord(StubStrategist([AgentTask(id="T1", goal="g")]),
               StubImplementer("failed"), StubAuditor("approve"), StubAuditor("approve"))
    res = c.run("goal")
    assert res.outcomes[0].outcome == "blocked"


def test_skipped_is_blocked_not_revise():
    c = _coord(StubStrategist([AgentTask(id="T1", goal="g")]),
               StubImplementer("skipped"), StubAuditor("approve"), StubAuditor("approve"))
    res = c.run("goal")
    assert res.outcomes[0].outcome == "blocked"


def test_revise_when_not_all_approve_but_no_block():
    c = _coord(StubStrategist([AgentTask(id="T1", goal="g")]),
               StubImplementer("done"), StubAuditor("approve"), StubAuditor("revise"))
    res = c.run("goal")
    assert res.outcomes[0].outcome == "revise"


def test_empty_plan_yields_error_result():
    c = _coord(StubStrategist([], last_error="model offline"),
               StubImplementer(), StubAuditor(), StubAuditor())
    res = c.run("goal")
    assert res.outcomes == [] and res.error == "model offline"


def test_coordinator_audits_transitions(tmp_path):
    audit = AuditLog(tmp_path / "a.jsonl")
    c = _coord(StubStrategist([AgentTask(id="T1", goal="g")]),
               StubImplementer("done"), StubAuditor("approve"), StubAuditor("approve"),
               audit=audit)
    c.run("goal")
    events = [e["event"] for e in audit.read_all()]
    assert "orch.coordinator_start" in events
    assert "orch.task_outcome" in events
    assert "orch.coordinator_done" in events


def test_end_to_end_with_real_roles_stubbed_claude(tmp_path):
    # Drive the whole pipeline with real role classes + injected ask lambdas.
    audit = AuditLog(tmp_path / "a.jsonl")
    plan = json.dumps([{"id": "T1", "goal": "open notepad"}])
    report = json.dumps({"taskId": "T1", "status": "done", "summary": "ok"})
    approve = json.dumps({"severity": "low", "verdict": "approve", "message": "good"})

    c = Coordinator(
        strategist=Strategist(ask=lambda p: plan, audit=audit),
        implementer=Implementer(ask=lambda p: report, audit=audit),
        codex=CodexAuditor(ask=lambda p: approve, audit=audit),
        northstar=NorthstarAuditor(ask=lambda p: approve, audit=audit),
        audit=audit)
    res = c.run("write a note")
    assert res.accepted == 1
    assert "T1" in res.to_markdown()


def test_result_to_dict_shape():
    c = _coord(StubStrategist([AgentTask(id="T1", goal="g")]),
               StubImplementer("done"), StubAuditor("approve"), StubAuditor("approve"))
    d = c.run("goal").to_dict()
    assert d["taskCount"] == 1 and d["accepted"] == 1
    assert d["outcomes"][0]["outcome"] == "accepted"
