"""Full-stack integration test of the live-AI `do` loop with stubs.

Exercises the whole chain end-to-end WITHOUT Claude or a real desktop:
  stubbed AI planner -> TaskLoop (with perceiver) -> safety-gated executor ->
  tool.run -> reliable tool writes+verifies a file -> loop verifies -> audit ->
  HTML replay. Proves the wiring holds together.
"""

import json

from desktop_worker.actions.backends import NullInputBackend
from desktop_worker.actions.executor import ActionExecutor
from desktop_worker.audit.log import AuditLog
from desktop_worker.audit.report import build_html_report
from desktop_worker.broker.cli_broker import ElevatedCliBroker
from desktop_worker.loop.claude_cli_planner import ClaudeCliPlanner
from desktop_worker.loop.task_loop import TaskLoop
from desktop_worker.observation.backends import NullDesktopBackend
from desktop_worker.observation.observer import Observer
from desktop_worker.perception import Perceiver, NullOcrBackend, NullUiaBackend
from desktop_worker.safety.emergency_stop import EmergencyStop
from desktop_worker.safety.policy import PermissionPolicy, auto_approve
from desktop_worker.tools import CreateTextFileTool, ToolRegistry


def _scripted_ask(responses):
    """Return an `ask` that yields each canned claude envelope in turn."""
    it = iter(responses)

    def ask(_prompt):
        try:
            inner = next(it)
        except StopIteration:
            inner = '{"done": true, "reasoning": "no more steps"}'
        return json.dumps({"type": "result", "is_error": False, "result": inner})

    return ask


def test_full_do_loop_uses_tool_creates_file_and_replays(tmp_path):
    desktop = tmp_path / "Desktop"
    desktop.mkdir()

    audit = AuditLog(tmp_path / "audit.jsonl", session_id="ai-do", task_id="task")
    policy = PermissionPolicy(approval_callback=auto_approve)
    estop = EmergencyStop()
    broker = ElevatedCliBroker(audit=audit, policy=policy,
                               cli_artifacts_dir=tmp_path / "cli", estop=estop,
                               elevator=None)
    executor = ActionExecutor(audit=audit, policy=policy,
                              input_backend=NullInputBackend(), broker=broker, estop=estop)

    # The AI's "reliable hands": a tool that writes the file directly (broker=None
    # so no real app launch — pure, deterministic for the test).
    tools = ToolRegistry()
    tools.register(CreateTextFileTool(desktop_dir=str(desktop), broker=None))
    executor.tools = tools

    observer = Observer(NullDesktopBackend(), screenshots_dir=tmp_path / "s")
    perceiver = Perceiver(ocr=NullOcrBackend(), uia=NullUiaBackend())

    # Step 1: AI calls the tool. Step 2: AI verifies the file and says done.
    target = str(desktop / "notes.txt")
    planner = ClaudeCliPlanner(
        task="create notes.txt on the desktop with content hello", broker=None, cwd=".",
        audit=audit, tools_catalog=tools.catalog(),
        ask=_scripted_ask([
            '{"reasoning": "use the reliable tool", "action": {"type": "tool.run", '
            '"tool": "create_text_file", "args": {"filename": "notes", "content": "hello"}}, '
            '"description": "create notes.txt"}',
            '{"done": true, "reasoning": "file created and verified"}',
        ]),
    )

    loop = TaskLoop(task_id="task", planner=planner, observer=observer,
                    executor=executor, audit=audit, estop=estop, perceiver=perceiver)
    report = loop.run()

    # 1) the whole loop completed
    assert report.completed is True
    assert report.steps_run == 1 and report.failures == 0

    # 2) the tool actually wrote + the content is exact
    from pathlib import Path
    assert Path(target).read_text(encoding="utf-8") == "hello"

    # 3) the AI's tool call was audited as an executed action
    events = [e["event"] for e in audit.read_all()]
    assert "planner.step" in events
    assert "action.executed" in events
    assert "task.finished" in events

    # 4) a human-readable replay can be built from the audit
    html = build_html_report(audit.read_all(), title="integration")
    assert "create_text_file" in html
    assert "<!DOCTYPE html>" in html


def test_full_do_loop_emergency_stop_halts(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    policy = PermissionPolicy(approval_callback=auto_approve)
    estop = EmergencyStop()
    broker = ElevatedCliBroker(audit=audit, policy=policy,
                               cli_artifacts_dir=tmp_path / "cli", estop=estop, elevator=None)
    executor = ActionExecutor(audit=audit, policy=policy,
                              input_backend=NullInputBackend(), broker=broker, estop=estop)
    observer = Observer(NullDesktopBackend(), screenshots_dir=tmp_path / "s")

    planner = ClaudeCliPlanner(
        task="t", broker=None, cwd=".", audit=audit,
        ask=_scripted_ask(['{"reasoning":"move","action":{"type":"mouse.move","x":1,"y":1}}']),
    )
    loop = TaskLoop(task_id="t", planner=planner, observer=observer,
                    executor=executor, audit=audit, estop=estop)
    estop.stop("user pressed stop")          # halt before the loop runs
    report = loop.run()
    assert report.halted is True
    assert report.steps_run == 0             # nothing executed after stop
