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
