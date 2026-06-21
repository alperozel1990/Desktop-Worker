"""Command-line entry point.

Subcommands (Phase 1/2 scope — a real UI is Phase 7):

    desktop-worker status     show config, backends, and process elevation
    desktop-worker observe    capture one structured observation, print JSON
    desktop-worker demo       run the scripted demo task through the full loop
    desktop-worker estop      write the emergency-stop sentinel file
    desktop-worker clear-stop remove the emergency-stop sentinel file

The demo proves the observe-plan-act-verify-log loop end-to-end using Null
backends (no real desktop input), writing artifacts + audit log + report.
"""

from __future__ import annotations

import argparse
import json
import sys

from desktop_worker import __version__
from desktop_worker.app import Session
from desktop_worker.broker.cli_broker import is_process_elevated
from desktop_worker.config import Config
from desktop_worker.loop.task_loop import ScriptedPlanner, TaskLoop
from desktop_worker.safety.policy import PermissionPolicy, auto_approve


def _cmd_status(args: argparse.Namespace) -> int:
    cfg = Config.from_env()
    session = Session(cfg, prefer_real_backends=not args.null)
    print(f"Desktop-Worker {__version__}")
    print(f"  session/task : {cfg.session_id}/{cfg.task_id}")
    print(f"  artifacts    : {cfg.task_dir}")
    print(f"  estop file   : {cfg.estop_file} (present={cfg.estop_file.exists()})")
    print(f"  process admin: {is_process_elevated()}")
    print(f"  backends     : {session.backend_names()}")
    print(f"  dry_run      : {cfg.dry_run}")
    return 0


def _cmd_observe(args: argparse.Namespace) -> int:
    cfg = Config.from_env()
    session = Session(cfg, prefer_real_backends=not args.null)
    obs = session.observer.observe("manual", screenshot=not args.no_screenshot)
    print(json.dumps(obs.to_dict(), indent=2))
    return 0


def _cmd_demo(args: argparse.Namespace) -> int:
    cfg = Config(session_id="session-demo", task_id="task-demo", dry_run=args.dry_run)
    # The demo auto-approves so it can show the broker path end-to-end; real
    # sessions use deny_all and a UI prompt.
    policy = PermissionPolicy(approval_callback=auto_approve)
    session = Session(cfg, policy=policy, prefer_real_backends=not args.null)

    # A small structured script exercising every Phase-1 action family safely.
    steps = ScriptedPlanner.from_dicts([
        {"action": {"type": "clipboard.set", "text": "desktop-worker"},
         "description": "Put a marker on the clipboard"},
        {"action": {"type": "clipboard.get"},
         "description": "Read it back and verify",
         "expectedResult": {"clipboardEquals": "desktop-worker"}},
        {"action": {"type": "mouse.move", "x": 100, "y": 100},
         "description": "Move the cursor"},
        {"action": {"type": "keyboard.hotkey", "keys": ["CTRL", "L"]},
         "description": "Send a hotkey"},
        {"action": {"type": "wait", "durationMs": 1},
         "description": "Brief wait"},
    ])

    loop = TaskLoop(
        task_id=cfg.task_id, planner=steps, observer=session.observer,
        executor=session.executor, audit=session.audit, estop=session.estop,
        limits=cfg.limits,
    )
    report = loop.run()
    cfg.report_file.write_text(report.to_markdown(), encoding="utf-8")

    print(report.to_markdown())
    print(f"Audit log : {cfg.audit_file}")
    print(f"Report    : {cfg.report_file}")
    print(f"Backends  : {session.backend_names()}")
    return 0 if report.completed else 1


def _cmd_estop(_args: argparse.Namespace) -> int:
    cfg = Config.from_env()
    session = Session(cfg)
    session.estop.stop("emergency stop via CLI")
    print(f"Emergency stop set: {cfg.estop_file}")
    return 0


def _cmd_clear_stop(_args: argparse.Namespace) -> int:
    cfg = Config.from_env()
    session = Session(cfg)
    session.estop.clear()
    print(f"Emergency stop cleared: {cfg.estop_file}")
    return 0


def _cmd_create_file(args: argparse.Namespace) -> int:
    """Visibly create a desktop text file with content (Phase 5 workflow)."""
    from desktop_worker.workflows import create_desktop_text_file
    from desktop_worker.workflows.desktop_ui import get_desktop_dir, get_desktop_ui

    cfg = Config(session_id="workflow", task_id="create-file")
    session = Session(cfg, prefer_real_backends=not args.null)
    ui = get_desktop_ui(prefer_real=not args.null)
    screen = session.desktop_backend.screen()
    desktop_dir = args.desktop or get_desktop_dir()

    print(f"Creating {args.name}.txt on {desktop_dir} with text {args.text!r} ...")
    print("Watch your screen. Emergency stop: run `python -m desktop_worker estop`.")
    result = create_desktop_text_file(
        args.text, executor=session.executor, ui=ui,
        desktop_dir=desktop_dir, screen_size=(screen.width, screen.height),
        filename=args.name,
    )
    print(result.to_markdown())
    cfg.report_file.write_text(result.to_markdown(), encoding="utf-8")
    print(f"Audit log: {cfg.audit_file}")
    return 0 if result.success else 1


def _console_approver(request) -> bool:
    """Interactive approval for high-risk actions; deny if not a TTY (headless)."""
    try:
        if not sys.stdin or not sys.stdin.isatty():
            return False
        print(f"\n[APPROVAL NEEDED] risk={request.risk.value} :: {request.summary}")
        return input("  Allow this action? [y/N] ").strip().lower() in ("y", "yes")
    except Exception:
        return False


def _cmd_do(args: argparse.Namespace) -> int:
    """Live AI-driven task: Claude decides each action; the agent performs it.

    Genuine dynamic control — no scripted steps. Claude (your logged-in CLI, no
    API key) chooses the next structured action from the perceived screen each
    step; the safety-gated executor performs it; the loop verifies and continues.
    """
    from desktop_worker.config import Limits
    from desktop_worker.loop.claude_cli_planner import ClaudeCliPlanner, claude_available
    from desktop_worker.loop.task_loop import TaskLoop
    from desktop_worker.perception import Perceiver, get_ocr_backend, get_uia_backend
    from desktop_worker.safety.policy import PermissionPolicy, RiskLevel

    real = not args.null
    cfg = Config(session_id="ai-do", task_id="task")
    # Low/medium actions run so you can WATCH; HIGH-risk (e.g. dangerous CLI) asks.
    policy = PermissionPolicy(approval_callback=_console_approver,
                              approval_threshold=RiskLevel.HIGH)
    session = Session(cfg, policy=policy, prefer_real_backends=real)

    cwd = str(cfg.artifacts_root.parent)
    if real and not claude_available(session.broker, cwd):
        print("ERROR: the `claude` CLI is not logged in. Run `claude auth status`.")
        return 2

    from desktop_worker.workflows.desktop_ui import get_desktop_dir

    screen = session.desktop_backend.screen()
    desktop_dir = get_desktop_dir()
    env_context = (
        f"- OS: Windows. Screen size: {screen.width}x{screen.height} "
        f"(empty desktop center is about {screen.width // 2},{screen.height // 2}).\n"
        f"- Desktop folder: {desktop_dir}\n"
        f"- Valid working directory for cli.run: {cwd}\n"
        "- You control the desktop with mouse + keyboard. To open an app, prefer the "
        "keyboard (e.g. hotkey WIN+R then type the app name then ENTER) or clicking a "
        "visible element by elementId.\n"
        "- cli.run is ONLY for short non-interactive commands and BLOCKS until they "
        "exit — NEVER use it to launch GUI apps (notepad, chrome). Its cwd must exist.\n"
        "- To create a desktop text file you can right-click an empty desktop spot, "
        "choose New then Text Document; menu items appear as elements to click by id."
    )
    perceiver = Perceiver(ocr=get_ocr_backend(real), uia=get_uia_backend(real))
    planner = ClaudeCliPlanner(task=args.task, broker=session.broker, cwd=cwd,
                               audit=session.audit, env_context=env_context,
                               vision=args.vision)
    if args.vision:
        print(f"Vision fallback ON: a screenshot is sent to Claude when accessibility "
              f"data is sparse. On low-UIA apps (Electron/games) that can be MOST steps, "
              f"each costing notably more Claude usage. Capped at {planner.max_vision_steps} "
              f"vision steps per task, then text-only.")

    def show_step(step) -> None:
        if planner.last_reasoning:
            print(f"\n[AI] {planner.last_reasoning}")
        print(f"  -> {step.action}  ({step.description})")

    loop = TaskLoop(
        task_id=cfg.task_id, planner=planner, observer=session.observer,
        executor=session.executor, audit=session.audit, estop=session.estop,
        perceiver=perceiver, settle_s=0.6, on_step=show_step, stall_guard=True,
        limits=Limits(max_actions_per_task=args.max_actions,
                      max_task_seconds=args.max_seconds),
    )

    print(f"TASK: {args.task}")
    print("Claude decides each step live. Emergency stop: `python -m desktop_worker estop` "
          "(in another window).\n")
    report = loop.run()
    print("\n" + report.to_markdown())
    if planner.last_done_reason:
        print(f"AI final note: {planner.last_done_reason}")
    if args.vision:
        print(f"Vision steps used: {planner.vision_steps_used} (each sent a screenshot "
              f"to Claude — the higher-cost steps).")
    # Friendly hint when the AI couldn't run because of the Claude account limit.
    err = (planner.last_error or "").lower()
    if "spend limit" in err or "usage" in err or "rate limit" in err:
        print("\nNOTE: your Claude usage/spend limit was reached — this is an account "
              "limit, not an app error. Each AI step calls Claude. Wait for the reset "
              "or raise it at claude.ai/settings/usage. (The scripted `create-file` "
              "demo works without Claude.)")
    print(f"Audit log: {cfg.audit_file}")
    return 0 if report.completed else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="desktop-worker", description=__doc__)
    p.add_argument("--null", action="store_true",
                   help="force Null backends (no real desktop control)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("status", help="show config and backends")
    s.set_defaults(func=_cmd_status)

    o = sub.add_parser("observe", help="capture one structured observation")
    o.add_argument("--no-screenshot", action="store_true")
    o.set_defaults(func=_cmd_observe)

    d = sub.add_parser("demo", help="run the scripted demo task loop")
    d.add_argument("--dry-run", action="store_true")
    d.set_defaults(func=_cmd_demo)

    e = sub.add_parser("estop", help="trigger emergency stop")
    e.set_defaults(func=_cmd_estop)

    c = sub.add_parser("clear-stop", help="clear emergency stop")
    c.set_defaults(func=_cmd_clear_stop)

    cf = sub.add_parser("create-file",
                        help="visibly create a desktop text file with content")
    cf.add_argument("--text", default="başlıyoruz", help="content to type into the file")
    cf.add_argument("--name", default="dw-demo", help="file name (without .txt)")
    cf.add_argument("--desktop", default=None, help="override the desktop directory")
    cf.set_defaults(func=_cmd_create_file)

    do = sub.add_parser("do", help="give a natural-language task; the AI drives it live")
    do.add_argument("task", help="the task in plain language, e.g. \"open Notepad and type hi\"")
    do.add_argument("--max-actions", type=int, default=15, help="max actions before stopping")
    do.add_argument("--max-seconds", type=int, default=300, help="max task time")
    do.add_argument("--vision", action="store_true",
                    help="let Claude SEE a screenshot when accessibility data is sparse "
                         "(works on more apps; costs more Claude usage)")
    do.set_defaults(func=_cmd_do)
    return p


def main(argv: list[str] | None = None) -> int:
    # The Windows console is often cp1252; make stdout/stderr tolerate non-ASCII
    # (e.g. Turkish content) so printing a report never crashes the command.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:
            pass
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
