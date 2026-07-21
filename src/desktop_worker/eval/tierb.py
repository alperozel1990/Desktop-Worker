"""Tier B — full AI task evaluation (DW-EVAL-TIERB).

Tier A grades the tool SURFACE with no model in the loop. Tier B grades the thing
the surface exists for: can an AI actually finish a task on this desktop?

**This tier spends Claude quota.** Every planner step is one `claude` CLI call
against the user's subscription, so cost control is part of the design rather than
an afterthought:

* a per-task action cap (a runaway task cannot drain the account),
* a run-wide step budget that halts the suite when exhausted,
* the ACTUAL number of AI calls reported back, so the cost is visible after the
  fact rather than guessed at.

Scoring uses the same deterministic oracles as Tier A. The AI's own claim that it
finished is recorded but never trusted as the verdict — "the agent said it worked"
is exactly the failure mode oracles exist to catch.
"""

from __future__ import annotations

from typing import Any, Callable, Optional


class AiStepBudget:
    """Shared, run-wide ceiling on AI planner steps.

    Deliberately mutable and shared across tasks: the point is that the SUITE
    cannot exceed a total cost, not merely that each task is individually bounded.
    """

    def __init__(self, total: int) -> None:
        self.total = max(0, int(total))
        self.spent = 0

    @property
    def remaining(self) -> int:
        return max(0, self.total - self.spent)

    @property
    def exhausted(self) -> bool:
        return self.remaining <= 0

    def charge(self, steps: int) -> None:
        self.spent += max(0, int(steps))

    def to_dict(self) -> dict[str, int]:
        return {"total": self.total, "spent": self.spent, "remaining": self.remaining}


def build_ai_probe(
    task_text: str,
    *,
    budget: AiStepBudget,
    max_actions: int = 12,
    max_seconds: int = 180,
    runner: Optional[Callable[..., Any]] = None,
) -> Callable[[Any], dict[str, Any]]:
    """Return a probe that drives one real AI task and reports what happened.

    ``runner`` is injectable so the whole tier is testable without spending a
    single token; the default builds the real Claude-CLI loop.
    """

    def probe(ctx: Any) -> dict[str, Any]:
        if budget.exhausted:
            # Refusing loudly beats silently running a cheaper, different thing.
            return {
                "steps": 0,
                "ok": False,
                "skipped": True,
                "reason": (
                    f"AI step budget exhausted ({budget.spent}/{budget.total}); "
                    "raise --max-ai-steps to run this task"
                ),
                "budget": budget.to_dict(),
            }

        run = runner or _run_real_ai_task
        allowed = min(max_actions, budget.remaining)
        try:
            outcome = run(
                task_text=task_text,
                max_actions=allowed,
                max_seconds=max_seconds,
            )
        except Exception as exc:
            return {
                "steps": 0,
                "ok": False,
                "reason": f"AI run raised {type(exc).__name__}: {exc}",
                "budget": budget.to_dict(),
            }

        steps = int(outcome.get("steps") or 0)
        budget.charge(steps)
        return {
            "steps": steps,
            # The AI's own completion claim — recorded, never the verdict. The
            # oracle decides; this is here so a disagreement is visible.
            "aiClaimedDone": bool(outcome.get("completed")),
            "aiFinalNote": outcome.get("doneReason") or "",
            "aiCalls": steps,
            "ok": bool(outcome.get("completed")),
            "budget": budget.to_dict(),
            "error": outcome.get("error"),
        }

    return probe


def _run_real_ai_task(*, task_text: str, max_actions: int, max_seconds: int) -> dict[str, Any]:
    """Drive one task through the real Claude-CLI planner loop.

    Mirrors the wiring of the `do` command deliberately: Tier B must measure the
    path a user actually gets, not a simplified stand-in that would score better.
    """
    from desktop_worker.app import Session
    from desktop_worker.config import Config, Limits
    from desktop_worker.geometry import get_canvas_locator
    from desktop_worker.geometry.paint_setup import get_paint_ui
    from desktop_worker.loop.claude_cli_planner import ClaudeCliPlanner, claude_available
    from desktop_worker.loop.task_loop import TaskLoop
    from desktop_worker.perception import Perceiver, get_ocr_backend, get_uia_backend
    from desktop_worker.safety import build_policy
    from desktop_worker.safety.policy import auto_approve
    from desktop_worker.tools import (CreateTextFileTool, DragDropTool, FocusWindowTool,
                                      OpenAppTool, OpenUrlTool, SketchTool, ToolRegistry)
    from desktop_worker.workflows.desktop_ui import get_desktop_dir

    cfg = Config(session_id="eval-tierb", task_id="task")
    policy = build_policy("standard", auto_approve,
                          app_allowlist=cfg.app_allowlist, app_denylist=cfg.app_denylist)
    session = Session(cfg, policy=policy, prefer_real_backends=True)
    cwd = str(cfg.artifacts_root.parent)

    if not claude_available(session.broker, cwd):
        return {"completed": False, "steps": 0,
                "error": "the `claude` CLI is not logged in (run `claude auth status`)"}

    screen = session.desktop_backend.screen()
    desktop_dir = get_desktop_dir()
    env_context = (
        f"- OS: Windows. Screen size: {screen.width}x{screen.height}.\n"
        f"- Desktop folder: {desktop_dir}\n"
        f"- Valid working directory for cli.run: {cwd}\n"
        "- You control the desktop with mouse + keyboard. To open an app prefer the "
        "`open_app` tool, or the keyboard (WIN+R, type the name, ENTER).\n"
        "- cli.run is ONLY for short non-interactive commands and BLOCKS until they "
        "exit — NEVER use it to launch GUI apps.\n"
        "- To create a text file, prefer the `create_text_file` tool: it writes and "
        "verifies the file instead of driving a fragile GUI sequence.\n"
        "- If the task is impossible, say so and stop rather than inventing a result."
    )

    tools = ToolRegistry()
    tools.register(CreateTextFileTool(desktop_dir=desktop_dir, broker=session.broker))
    tools.register(OpenAppTool(desktop_dir=desktop_dir, broker=session.broker, policy=policy))
    tools.register(OpenUrlTool(desktop_dir=desktop_dir, broker=session.broker))
    tools.register(FocusWindowTool())
    tools.register(DragDropTool(input_backend=session.input_backend, estop=session.estop))
    tools.register(SketchTool(input_backend=session.input_backend,
                              canvas_locator=get_canvas_locator(True),
                              estop=session.estop, paint_ui=get_paint_ui(True)))
    session.executor.tools = tools

    perceiver = Perceiver(ocr=get_ocr_backend(True), uia=get_uia_backend(True))
    planner = ClaudeCliPlanner(task=task_text, broker=session.broker, cwd=cwd,
                               audit=session.audit, env_context=env_context,
                               vision=False, tools_catalog=tools.catalog(),
                               frugal=True)  # frugal: leaner prompts, less quota per step

    loop = TaskLoop(
        task_id=cfg.task_id, planner=planner, observer=session.observer,
        executor=session.executor, audit=session.audit, estop=session.estop,
        perceiver=perceiver, settle_s=0.6, stall_guard=True,
        limits=Limits(max_actions_per_task=max_actions, max_task_seconds=max_seconds),
    )
    report = loop.run()
    # `steps_run` is the planner-step count and therefore the Claude call count.
    # Read it explicitly rather than with a defaulting getattr: an earlier version
    # asked for a field that does not exist ("steps") and silently got 0, so the
    # budget reported 0/30 spent while real calls were being made. A cost counter
    # that fails to zero is worse than no counter — it silently disables the
    # ceiling it exists to enforce.
    if not hasattr(report, "steps_run"):
        raise AttributeError(
            "TaskReport has no `steps_run`; the AI cost counter cannot be trusted "
            "(refusing to report a possibly-wrong zero)"
        )
    return {
        "completed": bool(report.completed),
        "steps": int(report.steps_run),
        "doneReason": planner.last_done_reason or "",
        "error": planner.last_error or "",
    }
