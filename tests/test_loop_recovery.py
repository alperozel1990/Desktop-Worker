"""DW-LOOP-RECOVERY — retry / re-plan / safe-stop + time limit (requirements §15)."""

from desktop_worker.actions.backends import NullInputBackend
from desktop_worker.actions.executor import ActionExecutor
from desktop_worker.audit.log import AuditLog
from desktop_worker.broker.cli_broker import ElevatedCliBroker
from desktop_worker.config import Limits
from desktop_worker.loop.task_loop import PlannedStep, ScriptedPlanner, TaskLoop
from desktop_worker.observation.backends import NullDesktopBackend
from desktop_worker.observation.observer import Observer
from desktop_worker.safety.emergency_stop import EmergencyStop
from desktop_worker.safety.policy import PermissionPolicy, auto_approve
from desktop_worker.schema.actions import parse_action


class FlakyInput(NullInputBackend):
    """Fails the first ``fail_times`` mouse.move calls, then behaves normally."""

    def __init__(self, fail_times: int = 0):
        super().__init__()
        self.fail_times = fail_times

    def move(self, x, y):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("flaky move")
        super().move(x, y)


def _build(tmp_path, planner, *, input_backend=None, desktop=None,
           limits=None, now=None, estop=None):
    audit = AuditLog(tmp_path / "audit.jsonl")
    policy = PermissionPolicy(approval_callback=auto_approve)
    es = estop or EmergencyStop()
    observer = Observer(desktop or NullDesktopBackend(),
                        screenshots_dir=tmp_path / "s", observations_dir=tmp_path / "o")
    broker = ElevatedCliBroker(audit=audit, policy=policy,
                               cli_artifacts_dir=tmp_path / "cli", estop=es)
    ex = ActionExecutor(audit=audit, policy=policy,
                        input_backend=input_backend or NullInputBackend(),
                        broker=broker, estop=es)
    kwargs = {}
    if now is not None:
        kwargs["now"] = now
    loop = TaskLoop(task_id="t", planner=planner, observer=observer,
                    executor=ex, audit=audit, estop=es,
                    limits=limits or Limits(), **kwargs)
    return loop, audit


class FailingType(NullInputBackend):
    """Always fails keyboard typing."""

    def type_text(self, text):
        raise RuntimeError("type failed")


class ReplanningPlanner(ScriptedPlanner):
    """Scripted, but can re-plan to a step that always succeeds."""

    def __init__(self, steps, replan_to):
        super().__init__(steps)
        self._replan_to = replan_to
        self.replans = 0

    def replan(self, failed, observation, history):
        self.replans += 1
        return self._replan_to


def test_retryable_action_failure_is_retried_then_succeeds(tmp_path):
    planner = ScriptedPlanner([PlannedStep(parse_action({"type": "mouse.move", "x": 1, "y": 1}),
                                           description="move")])
    loop, audit = _build(tmp_path, planner, input_backend=FlakyInput(fail_times=1),
                         limits=Limits(max_retries=3))
    report = loop.run()
    assert report.completed is True
    assert report.failures == 0          # final outcome is success
    assert report.steps_run == 1
    events = [e["event"] for e in audit.read_all()]
    assert "step.retry" in events        # a retry actually happened


def test_non_retryable_action_failure_stops_without_retry(tmp_path):
    planner = ScriptedPlanner([PlannedStep(parse_action({"type": "keyboard.type", "text": "hi"}),
                                           description="type")])
    loop, audit = _build(tmp_path, planner, input_backend=FailingType(),
                         limits=Limits(max_retries=3))
    report = loop.run()
    assert report.completed is False
    assert report.failures == 1
    events = [e["event"] for e in audit.read_all()]
    assert "step.retry" not in events    # keyboard.type must NOT be retried
    assert "step failed" in report.stop_reason


def test_verification_failure_retried_then_safe_stop(tmp_path):
    # clipboard.get returns "" (nothing set) but we expect "nope" -> verify fails.
    step = PlannedStep(parse_action({"type": "clipboard.get"}),
                       description="read", expected={"clipboardEquals": "nope"})
    loop, audit = _build(tmp_path, ScriptedPlanner([step]), limits=Limits(max_retries=2))
    report = loop.run()
    assert report.completed is False
    assert "verification failed" in report.stop_reason
    retries = [e for e in audit.read_all() if e["event"] == "step.retry"]
    assert len(retries) == 2             # retried exactly max_retries times


def test_replan_recovers_after_failure(tmp_path):
    failing = PlannedStep(parse_action({"type": "clipboard.get"}),
                          description="read", expected={"clipboardEquals": "nope"})
    recovery = PlannedStep(parse_action({"type": "mouse.move", "x": 2, "y": 2}),
                           description="recover")
    planner = ReplanningPlanner([failing], replan_to=recovery)
    loop, audit = _build(tmp_path, planner, limits=Limits(max_retries=1))
    report = loop.run()
    assert report.completed is True
    assert planner.replans == 1
    events = [e["event"] for e in audit.read_all()]
    assert "step.replanned" in events


def test_persistently_failing_retryable_action_is_bounded(tmp_path):
    planner = ScriptedPlanner([PlannedStep(parse_action({"type": "mouse.move", "x": 1, "y": 1}),
                                           description="move")])
    loop, audit = _build(tmp_path, planner, input_backend=FlakyInput(fail_times=99),
                         limits=Limits(max_retries=3))
    report = loop.run()
    assert report.completed is False
    retries = [e for e in audit.read_all() if e["event"] == "step.retry"]
    assert len(retries) == 3             # exactly max_retries, then safe-stop
    assert "step failed" in report.stop_reason


class AlwaysFailingReplanner(ScriptedPlanner):
    """Re-plans to a step that itself always fails verification — must not loop forever."""

    def __init__(self, steps, replan_to):
        super().__init__(steps)
        self._replan_to = replan_to
        self.replans = 0

    def replan(self, failed, observation, history):
        self.replans += 1
        return self._replan_to


def test_replan_is_bounded(tmp_path):
    failing = PlannedStep(parse_action({"type": "clipboard.get"}),
                          description="read", expected={"clipboardEquals": "nope"})
    planner = AlwaysFailingReplanner([failing], replan_to=failing)
    loop, audit = _build(tmp_path, planner, limits=Limits(max_retries=2))
    report = loop.run()
    assert report.completed is False
    assert planner.replans <= 2          # bounded, no infinite re-plan
    replanned = [e for e in audit.read_all() if e["event"] == "step.replanned"]
    assert len(replanned) <= 2


def test_window_focus_not_retried_as_unexecutable(tmp_path):
    # window.focus is not executor-dispatchable yet; it must fail fast, not retry-storm.
    planner = ScriptedPlanner([PlannedStep(parse_action({"type": "window.focus",
                                                         "titleContains": "Chrome"}),
                                           description="focus")])
    loop, audit = _build(tmp_path, planner, limits=Limits(max_retries=3))
    report = loop.run()
    assert report.completed is False
    assert "step.retry" not in [e["event"] for e in audit.read_all()]


def test_time_limit_enforced(tmp_path):
    ticks = iter([0.0, 1000.0, 2000.0])  # start, then elapsed >> limit
    planner = ScriptedPlanner([PlannedStep(parse_action({"type": "wait", "durationMs": 1}),
                                           description="wait")])
    loop, audit = _build(tmp_path, planner, limits=Limits(max_task_seconds=10),
                         now=lambda: next(ticks))
    report = loop.run()
    assert report.steps_run == 0
    assert "max task time" in report.stop_reason
    assert "task.timeout" in [e["event"] for e in audit.read_all()]


def test_time_limit_trips_inside_recovery(tmp_path):
    # Outer time-check passes (1s), action fails, then wall-clock trips mid-step.
    ticks = iter([0.0, 1.0, 1000.0, 2000.0])  # start, outer-check, inner-check
    planner = ScriptedPlanner([PlannedStep(parse_action({"type": "mouse.move", "x": 1, "y": 1}),
                                           description="move")])
    loop, audit = _build(tmp_path, planner, input_backend=FlakyInput(fail_times=99),
                         limits=Limits(max_task_seconds=10, max_retries=3),
                         now=lambda: next(ticks))
    report = loop.run()
    assert report.completed is False
    assert "during step" in report.stop_reason
    events = [e["event"] for e in audit.read_all()]
    assert "task.timeout" in events
    assert "step.retry" not in events    # tripped before any retry was spent
