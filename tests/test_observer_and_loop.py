from desktop_worker.actions.backends import NullInputBackend
from desktop_worker.actions.executor import ActionExecutor
from desktop_worker.audit.log import AuditLog
from desktop_worker.broker.cli_broker import ElevatedCliBroker
from desktop_worker.observation.backends import NullDesktopBackend
from desktop_worker.observation.observer import Observer
from desktop_worker.loop.task_loop import ScriptedPlanner, TaskLoop
from desktop_worker.safety.emergency_stop import EmergencyStop
from desktop_worker.safety.policy import PermissionPolicy, auto_approve


def test_observer_builds_structured_observation(tmp_path):
    backend = NullDesktopBackend(width=1280, height=720, cursor=(5, 6))
    obs = Observer(backend, screenshots_dir=tmp_path / "shots",
                   observations_dir=tmp_path / "obs").observe("t")
    d = obs.to_dict()
    assert d["screen"]["width"] == 1280
    assert d["cursor"] == {"x": 5, "y": 6}
    assert d["activeWindow"]["title"] == "NullDesktop"
    assert d["screenshotRef"]  # artifact reference present
    # observation persisted
    assert list((tmp_path / "obs").glob("*.json"))


def _loop(tmp_path, steps, estop=None):
    audit = AuditLog(tmp_path / "audit.jsonl")
    policy = PermissionPolicy(approval_callback=auto_approve)
    es = estop or EmergencyStop()
    backend = NullDesktopBackend()
    observer = Observer(backend, screenshots_dir=tmp_path / "s", observations_dir=tmp_path / "o")
    broker = ElevatedCliBroker(audit=audit, policy=policy, cli_artifacts_dir=tmp_path / "cli", estop=es)
    ex = ActionExecutor(audit=audit, policy=policy, input_backend=NullInputBackend(),
                        broker=broker, estop=es)
    planner = ScriptedPlanner.from_dicts(steps)
    return TaskLoop(task_id="t", planner=planner, observer=observer,
                    executor=ex, audit=audit, estop=es), audit


def test_loop_runs_to_completion(tmp_path):
    steps = [
        {"action": {"type": "clipboard.set", "text": "X"}, "description": "set"},
        {"action": {"type": "clipboard.get"}, "description": "get",
         "expectedResult": {"clipboardEquals": "X"}},
        {"action": {"type": "mouse.move", "x": 1, "y": 1}, "description": "move"},
    ]
    loop, audit = _loop(tmp_path, steps)
    report = loop.run()
    assert report.completed is True
    assert report.halted is False
    assert report.steps_run == 3
    assert report.failures == 0
    # verification of clipboard step passed
    events = [e["event"] for e in audit.read_all()]
    assert "task.started" in events
    assert "task.finished" in events
    assert "step.completed" in events


def test_loop_halts_on_emergency_stop(tmp_path):
    es = EmergencyStop()
    steps = [{"action": {"type": "mouse.move", "x": 1, "y": 1}, "description": "move"}]
    loop, _ = _loop(tmp_path, steps, estop=es)
    es.stop("halt before run")
    report = loop.run()
    assert report.halted is True
    assert report.steps_run == 0


def test_report_markdown(tmp_path):
    steps = [{"action": {"type": "wait", "durationMs": 1}, "description": "wait"}]
    loop, _ = _loop(tmp_path, steps)
    report = loop.run()
    md = report.to_markdown()
    assert "# Task Report" in md
    assert "wait" in md
