"""DW-PERCEPTION-WIRE — Perceiver wired into the loop so elements reach audit/AI."""

import dataclasses

from desktop_worker.actions.backends import NullInputBackend
from desktop_worker.actions.executor import ActionExecutor
from desktop_worker.audit.log import AuditLog
from desktop_worker.broker.cli_broker import ElevatedCliBroker
from desktop_worker.loop.task_loop import ScriptedPlanner, TaskLoop
from desktop_worker.observation.backends import NullDesktopBackend
from desktop_worker.observation.observer import Observer
from desktop_worker.safety.emergency_stop import EmergencyStop
from desktop_worker.safety.policy import PermissionPolicy, auto_approve
from desktop_worker.schema.observations import Element


class FakePerceiver:
    def __init__(self):
        self.calls = 0

    def perceive(self, observation):
        self.calls += 1
        el = Element(id="e1", type="button", bounds=(0, 0, 10, 10),
                     source="uia", text="Go")
        return dataclasses.replace(observation, elements=(el,))


def _loop(tmp_path, steps, *, perceiver=None):
    audit = AuditLog(tmp_path / "audit.jsonl")
    policy = PermissionPolicy(approval_callback=auto_approve)
    es = EmergencyStop()
    observer = Observer(NullDesktopBackend(), screenshots_dir=tmp_path / "s",
                        observations_dir=tmp_path / "o")
    broker = ElevatedCliBroker(audit=audit, policy=policy,
                               cli_artifacts_dir=tmp_path / "cli", estop=es)
    ex = ActionExecutor(audit=audit, policy=policy, input_backend=NullInputBackend(),
                        broker=broker, estop=es)
    loop = TaskLoop(task_id="t", planner=ScriptedPlanner.from_dicts(steps),
                    observer=observer, executor=ex, audit=audit, estop=es,
                    perceiver=perceiver)
    return loop, audit


def test_loop_enriches_observations_when_perceiver_present(tmp_path):
    fake = FakePerceiver()
    steps = [{"action": {"type": "wait", "durationMs": 1}, "description": "w"}]
    loop, audit = _loop(tmp_path, steps, perceiver=fake)
    loop.run()
    planned = [e for e in audit.read_all() if e["event"] == "step.planned"][0]
    assert planned["elements"][0]["text"] == "Go"      # elements reach the audit
    assert fake.calls >= 1                              # perceiver actually invoked


def test_loop_unchanged_without_perceiver(tmp_path):
    steps = [{"action": {"type": "wait", "durationMs": 1}, "description": "w"}]
    loop, audit = _loop(tmp_path, steps, perceiver=None)
    report = loop.run()
    assert report.completed is True
    planned = [e for e in audit.read_all() if e["event"] == "step.planned"][0]
    assert planned.get("elements", []) == []           # no elements, no regression
