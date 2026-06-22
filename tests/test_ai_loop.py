"""Tests for the live AI-driven loop pieces (element targeting, outcome, guards).

The real claude CLI is stubbed; no real service is called and no desktop is driven.
"""

import json

from desktop_worker.actions.backends import NullInputBackend
from desktop_worker.actions.executor import ActionExecutor
from desktop_worker.audit.log import AuditLog
from desktop_worker.broker.cli_broker import ElevatedCliBroker
from desktop_worker.config import Limits
from desktop_worker.loop.claude_cli_planner import ClaudeCliPlanner, build_planner_prompt
from desktop_worker.loop.task_loop import PlannedStep, TaskLoop
from desktop_worker.observation.backends import NullDesktopBackend
from desktop_worker.observation.observer import Observer
from desktop_worker.safety.emergency_stop import EmergencyStop
from desktop_worker.safety.policy import PermissionPolicy, auto_approve
from desktop_worker.schema.actions import parse_action
from desktop_worker.schema.observations import Cursor, Element, Observation, Screen


def _obs_with_element(eid="uia-2"):
    el = Element(id=eid, type="button", bounds=(100, 200, 200, 240),
                 source="uia", text="New")
    return Observation(screen=Screen(1920, 1080), cursor=Cursor(0, 0), elements=(el,))


def _envelope(inner: str) -> str:
    return json.dumps({"type": "result", "is_error": False, "result": inner})


def _planner(resp):
    return ClaudeCliPlanner(task="t", broker=None, cwd=".", ask=lambda p: resp)


class _FakeCliResult:
    def __init__(self, stdout):
        self.stdoutRef = None
        self.stdoutTail = stdout
        self.blocked = False
        self.exitCode = 0


class FakeBroker:
    def __init__(self, stdout):
        self.stdout = stdout
        self.commands = []
        self.cli_dir = None

    def run(self, command, cwd, **kw):
        self.commands.append(command)
        return _FakeCliResult(self.stdout)


def test_element_id_resolves_to_center_coords_for_mouse():
    resp = _envelope('{"action": {"type": "mouse.click"}, "elementId": "uia-2", '
                     '"reasoning": "click New", "description": "click"}')
    step = _planner(resp).next_step(_obs_with_element(), [])
    assert step is not None
    # center of (100,200,200,240) = (150, 220)
    assert step.action.params["x"] == 150
    assert step.action.params["y"] == 220


def test_element_id_not_injected_into_keyboard_action():
    resp = _envelope('{"action": {"type": "keyboard.type", "text": "hi"}, '
                     '"elementId": "uia-2", "reasoning": "type"}')
    step = _planner(resp).next_step(_obs_with_element(), [])
    assert step is not None
    assert step.action.type == "keyboard.type"
    assert "x" not in step.action.params      # keyboard.type must not get coords


def _obs_sparse(tmp_path, n_elements=0):
    shot = tmp_path / "shot.png"
    shot.write_bytes(b"\x89PNG\r\n")  # exists with image suffix
    els = tuple(
        Element(id=f"uia-{i}", type="button", bounds=(0, 0, 1, 1), source="uia")
        for i in range(n_elements)
    )
    return Observation(screen=Screen(800, 600), cursor=Cursor(0, 0),
                       elements=els, screenshotRef=str(shot))


def test_vision_off_by_default_no_screenshot(tmp_path):
    p = ClaudeCliPlanner(task="t", broker=None, cwd=".", ask=lambda x: "{}", vision=False)
    assert p._vision_path(_obs_sparse(tmp_path, 0)) == ""   # never, even with no elements


def test_vision_triggers_only_when_elements_sparse(tmp_path):
    p = ClaudeCliPlanner(task="t", broker=None, cwd=".", ask=lambda x: "{}",
                         vision=True, vision_threshold=4)
    # sparse (0 elements) -> vision uses the screenshot
    assert p._vision_path(_obs_sparse(tmp_path, 0)).endswith(".png")
    # rich (>= threshold elements) -> no vision (save cost)
    assert p._vision_path(_obs_sparse(tmp_path, 5)) == ""


def test_vision_step_cap_protects_quota(tmp_path):
    p = ClaudeCliPlanner(task="t", broker=None, cwd=".", ask=lambda x: "{}",
                         vision=True, vision_threshold=4, max_vision_steps=2)
    obs = _obs_sparse(tmp_path, 0)
    assert p._activate_vision(obs).endswith(".png")   # 1
    assert p._activate_vision(obs).endswith(".png")   # 2
    assert p._activate_vision(obs) == ""              # capped -> text-only
    assert p.vision_steps_used == 2


def test_vision_call_uses_read_tool_flags(tmp_path):
    resp = _envelope('{"done": true}')
    broker = FakeBroker(resp)
    p = ClaudeCliPlanner(task="t", broker=broker, cwd=".", vision=True, vision_threshold=4)
    p.next_step(_obs_sparse(tmp_path, 0), [])          # sparse -> vision path
    assert "allowedTools Read" in broker.commands[0]   # read tool enabled for vision
    assert "--max-turns 2" in broker.commands[0]


def test_unknown_element_id_is_rejected_not_misclicked():
    # A stale/hallucinated elementId must NOT become a coordless click.
    resp = _envelope('{"action": {"type": "mouse.click"}, "elementId": "uia-999", '
                     '"reasoning": "click ghost"}')
    p = _planner(resp)
    step = p.next_step(_obs_with_element("uia-2"), [])
    assert step is None
    assert p.last_outcome == "invalid"


def test_reasoning_and_outcome_captured():
    p = _planner(_envelope('{"action": {"type": "wait", "durationMs": 1}, "reasoning": "because"}'))
    p.next_step(_obs_with_element(), [])
    assert p.last_reasoning == "because"
    assert p.last_outcome == "step"


def test_outcome_done_vs_invalid():
    p = _planner(_envelope('{"done": true, "reasoning": "finished"}'))
    assert p.next_step(_obs_with_element(), []) is None
    assert p.last_outcome == "done"

    p2 = _planner("garbage not json")
    assert p2.next_step(_obs_with_element(), []) is None
    assert p2.last_outcome == "invalid"


def test_prompt_includes_env_context_and_element_ids():
    obs = _obs_with_element("uia-7")
    prompt = build_planner_prompt("do x", obs, [], env_context="- Desktop: C:/D")
    assert "uia-7" in prompt              # element id is targetable
    assert "C:/D" in prompt               # env context surfaced
    assert "elementId" in prompt          # instructed to target by id


def test_frugal_caps_elements_and_history(tmp_path):
    from desktop_worker.schema.observations import Screen
    many = tuple(Element(id=f"uia-{i}", type="button", bounds=(0, 0, 1, 1), source="uia",
                         text=f"btn{i}") for i in range(40))
    obs = Observation(screen=Screen(800, 600), cursor=Cursor(0, 0), elements=many)
    full = build_planner_prompt("t", obs, [], max_elements=40)
    frugal = build_planner_prompt("t", obs, [], max_elements=12)
    assert frugal.count("uia-") < full.count("uia-")    # fewer elements listed
    assert "uia-39" in full and "uia-39" not in frugal   # last element trimmed in frugal
    assert len(frugal) < len(full)                       # smaller prompt overall


def test_planner_frugal_sets_caps():
    p = ClaudeCliPlanner(task="t", broker=None, cwd=".", ask=lambda x: "{}", frugal=True)
    assert p._max_elements == 12 and p._max_history == 4
    p2 = ClaudeCliPlanner(task="t", broker=None, cwd=".", ask=lambda x: "{}")
    assert p2._max_elements == 40 and p2._max_history == 8


def test_prompt_shows_action_outcome_memory():
    # The AI must SEE that a past action had no visible effect (so it won't repeat).
    from desktop_worker.schema.results import ActionResult
    tried = ActionResult(
        action_type="keyboard.hotkey", success=True, startedAt="a", endedAt="b",
        detail={"actionStr": "keyboard.hotkey(keys=['CTRL', 'A'])", "screenChanged": False},
    )
    prompt = build_planner_prompt("t", _obs_with_element(), [tried])
    assert "CTRL" in prompt                       # what was tried is shown
    assert "no visible effect" in prompt          # and that it did nothing
    assert "do NOT repeat" in prompt or "different approach" in prompt


# --- loop integration (stubbed planner) ----------------------------------

class StubPlanner:
    """Returns scripted decisions; mimics ClaudeCliPlanner's last_outcome."""

    def __init__(self, decisions):
        self._d = list(decisions)
        self.last_outcome = "done"

    def next_step(self, obs, history):
        if not self._d:
            self.last_outcome = "done"
            return None
        item = self._d.pop(0)
        if item is None:
            self.last_outcome = "error"
            return None
        self.last_outcome = "step"
        return item


def _loop(tmp_path, planner, *, desktop=None, stall_guard=False, limits=None):
    audit = AuditLog(tmp_path / "audit.jsonl")
    policy = PermissionPolicy(approval_callback=auto_approve)
    es = EmergencyStop()
    observer = Observer(desktop or NullDesktopBackend(), screenshots_dir=tmp_path / "s")
    broker = ElevatedCliBroker(audit=audit, policy=policy, cli_artifacts_dir=tmp_path / "c",
                               estop=es, elevator=None)
    ex = ActionExecutor(audit=audit, policy=policy, input_backend=NullInputBackend(),
                        broker=broker, estop=es)
    return TaskLoop(task_id="t", planner=planner, observer=observer, executor=ex,
                    audit=audit, estop=es, stall_guard=stall_guard,
                    limits=limits or Limits()), audit


def test_loop_marks_failed_when_planner_errors(tmp_path):
    # A PERSISTENT invalid planner (past the retries) -> not completed.
    move = PlannedStep(parse_action({"type": "wait", "durationMs": 1}), description="w")
    loop, audit = _loop(tmp_path, FlakyPlanner(move, fail_n=99))
    report = loop.run()
    assert report.completed is False
    assert "AI could not decide" in report.stop_reason


def test_stall_guard_stops_on_no_progress(tmp_path):
    # Same action forever on a Null desktop (constant observation) -> stall guard.
    move = PlannedStep(parse_action({"type": "mouse.move", "x": 1, "y": 1}), description="m")
    loop, audit = _loop(tmp_path, StubPlanner([move] * 10), stall_guard=True)
    report = loop.run()
    assert report.completed is False
    assert "no progress" in report.stop_reason
    assert "task.stalled" in [e["event"] for e in audit.read_all()]


def _loop_with(tmp_path, steps, *, stall_guard=False):
    from desktop_worker.config import Limits
    planner = StubPlanner(list(steps))
    return _loop(tmp_path, planner, stall_guard=stall_guard, limits=Limits(max_actions_per_task=50))


def test_vision_forced_after_drawing(tmp_path):
    # After a stroke/drag, vision should fire even if the app is UIA-rich (the
    # drawing is on the canvas which UIA can't see).
    from desktop_worker.schema.results import ActionResult
    from desktop_worker.util import utc_now_iso
    rich = _obs_sparse(tmp_path, 20)        # 20 elements (>= threshold) — normally no vision
    p = ClaudeCliPlanner(task="draw", broker=None, cwd=".", ask=lambda x: '{"done":true}',
                         vision=True, vision_threshold=4)
    drew = [ActionResult(action_type="mouse.stroke", success=True,
                         startedAt=utc_now_iso(), endedAt=utc_now_iso())]
    # without a prior draw -> no vision (UIA rich); after a draw -> vision forced
    assert p._vision_path(rich, force=False) == ""
    assert p._vision_path(rich, force=True).endswith(".png")
    assert p._drew_last(drew) is True
    assert p._drew_last([]) is False


def test_stall_guard_ignores_drawing(tmp_path):
    # A loop of stroke actions on a constant (Null) observation must NOT trip the
    # stall guard — drawing legitimately doesn't change the element signature.
    from desktop_worker.loop.task_loop import _DRAW_ACTIONS
    assert "mouse.stroke" in _DRAW_ACTIONS and "mouse.drag" in _DRAW_ACTIONS
    move = PlannedStep(parse_action({"type": "mouse.stroke",
                                     "points": [[1, 1], [2, 2]]}), description="draw")
    loop, audit = _loop_with(tmp_path, [move] * 8, stall_guard=True)
    report = loop.run()
    # 8 strokes all ran (not killed by stall guard); ends by running out of planner steps
    assert report.steps_run == 8
    assert "task.stalled" not in [e["event"] for e in audit.read_all()]


def test_stall_guard_ignores_sketch_tool(tmp_path):
    # A `sketch` tool.run renders to the canvas (no UIA change) — like raw strokes it
    # must NOT trip the stall guard, or multi-primitive drawing tasks get killed.
    from desktop_worker.geometry.canvas import NullCanvasLocator
    from desktop_worker.tools import ToolRegistry
    from desktop_worker.tools.builtin import SketchTool
    audit = AuditLog(tmp_path / "audit.jsonl")
    policy = PermissionPolicy(approval_callback=auto_approve)
    es = EmergencyStop()
    observer = Observer(NullDesktopBackend(), screenshots_dir=tmp_path / "s")
    broker = ElevatedCliBroker(audit=audit, policy=policy, cli_artifacts_dir=tmp_path / "c",
                               estop=es, elevator=None)
    tools = ToolRegistry()
    tools.register(SketchTool(input_backend=NullInputBackend(),
                              canvas_locator=NullCanvasLocator(), estop=es))
    ex = ActionExecutor(audit=audit, policy=policy, input_backend=NullInputBackend(),
                        broker=broker, estop=es, tools=tools)
    cat = {"primitives": [{"kind": "circle", "center": [50, 50], "r": 20}]}
    step = PlannedStep(parse_action({"type": "tool.run", "tool": "sketch", "args": cat}),
                       description="draw")
    loop = TaskLoop(task_id="t", planner=StubPlanner([step] * 8), observer=observer,
                    executor=ex, audit=audit, estop=es, stall_guard=True,
                    limits=Limits(max_actions_per_task=50))
    report = loop.run()
    assert report.steps_run == 8
    assert "task.stalled" not in [e["event"] for e in audit.read_all()]


class FlakyPlanner:
    """Returns invalid (None) for the first `fail_n` calls, then a real step."""
    def __init__(self, step, fail_n):
        self._step = step; self._fail = fail_n; self.last_outcome = "invalid"; self.last_error = "empty"
    def next_step(self, obs, history):
        if self._fail > 0:
            self._fail -= 1; self.last_outcome = "invalid"; return None
        self.last_outcome = "step"; return self._step


def test_loop_retries_transient_invalid_planner(tmp_path):
    move = PlannedStep(parse_action({"type": "wait", "durationMs": 1}), description="w")
    # planner fails twice (transient) then succeeds -> loop should retry, not give up
    loop, audit = _loop(tmp_path, FlakyPlanner(move, fail_n=2))
    report = loop.run()
    retries = [e for e in audit.read_all() if e["event"] == "planner.retry"]
    assert len(retries) == 2
    assert report.steps_run >= 1          # recovered and ran the step


def test_loop_gives_up_after_persistent_invalid(tmp_path):
    move = PlannedStep(parse_action({"type": "wait", "durationMs": 1}), description="w")
    loop, audit = _loop(tmp_path, FlakyPlanner(move, fail_n=99))   # never recovers
    report = loop.run()
    assert report.completed is False
    assert "AI could not decide" in report.stop_reason
