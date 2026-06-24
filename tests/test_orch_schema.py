"""Tests for the orchestration handoff schema (Phase 6)."""

import pytest

from desktop_worker.orchestration import (
    AgentReport,
    AgentTask,
    AuditorFinding,
    OrchestrationValidationError,
    parse_agent_report,
    parse_agent_task,
    parse_finding,
)


# --- AgentTask ------------------------------------------------------------

def test_agent_task_round_trip():
    t = AgentTask(id="T1", goal="do x", acceptance=["a"], constraints=["c"],
                  forbidden_files=["safety/"])
    d = t.to_dict()
    assert d == {"id": "T1", "goal": "do x", "acceptance": ["a"],
                 "constraints": ["c"], "forbiddenFiles": ["safety/"]}
    assert parse_agent_task(d) == t


def test_agent_task_defaults():
    t = parse_agent_task({"id": "T1", "goal": "g"})
    assert t.acceptance == [] and t.forbidden_files == []


def test_agent_task_missing_required():
    with pytest.raises(OrchestrationValidationError):
        parse_agent_task({"goal": "no id"})


def test_agent_task_rejects_unexpected_field():
    with pytest.raises(OrchestrationValidationError):
        parse_agent_task({"id": "T", "goal": "g", "bogus": 1})


def test_agent_task_bad_list_type():
    with pytest.raises(OrchestrationValidationError):
        parse_agent_task({"id": "T", "goal": "g", "acceptance": "not-a-list"})


# --- AgentReport ----------------------------------------------------------

def test_agent_report_round_trip():
    r = AgentReport(task_id="T1", status="done", summary="ok", changes=["f.py"],
                    evidence=["12 tests"])
    assert parse_agent_report(r.to_dict()) == r


def test_agent_report_invalid_status():
    with pytest.raises(OrchestrationValidationError):
        parse_agent_report({"taskId": "T", "status": "weird"})


# --- AuditorFinding -------------------------------------------------------

def test_finding_round_trip():
    f = AuditorFinding(severity="high", verdict="revise", message="m", location="x.py:1")
    assert parse_finding(f.to_dict()) == f


def test_finding_invalid_verdict():
    with pytest.raises(OrchestrationValidationError):
        parse_finding({"severity": "low", "verdict": "nope"})


def test_finding_invalid_severity():
    with pytest.raises(OrchestrationValidationError):
        parse_finding({"severity": "huge", "verdict": "approve"})


def test_non_dict_payload():
    with pytest.raises(OrchestrationValidationError):
        parse_agent_task(["not", "a", "dict"])
