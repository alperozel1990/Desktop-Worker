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


def _cmd_switch_window(args: argparse.Namespace) -> int:
    """Bring an open window to the foreground by (part of) its title (Phase 5).

    Routes through the executor's `tool.run` (focus_window) so the focus change is
    emergency-stop-gated and audited like any other action.
    """
    from desktop_worker.schema.actions import parse_action
    from desktop_worker.tools import FocusWindowTool, ToolRegistry

    cfg = Config(session_id="workflow", task_id="switch-window")
    session = Session(cfg, prefer_real_backends=not args.null)
    tools = ToolRegistry()
    tools.register(FocusWindowTool())
    session.executor.tools = tools

    action = parse_action({"type": "tool.run", "tool": "focus_window",
                           "args": {"title_contains": args.title}})
    res = session.executor.execute(action)
    ok = getattr(res, "success", False)
    if ok:
        print(f"OK: focused a window matching {args.title!r}")
    else:
        print(f"FAILED: {getattr(res, 'error', '') or 'no matching window'}")
    print(f"Audit log: {cfg.audit_file}")
    return 0 if ok else 1


def _cmd_pick_file(args: argparse.Namespace) -> int:
    """Type a path into an already-open native file dialog and confirm (Phase 5)."""
    from desktop_worker.workflows import choose_file
    from desktop_worker.workflows.file_dialog import get_file_dialog_ui

    cfg = Config(session_id="workflow", task_id="pick-file")
    session = Session(cfg, prefer_real_backends=not args.null)
    ui = get_file_dialog_ui(prefer_real=not args.null)

    print(f"Filling the open file dialog with {args.path!r} (confirm={args.confirm}).")
    print("A file dialog must already be open. Emergency stop: `python -m desktop_worker estop`.")
    result = choose_file(args.path, executor=session.executor, ui=ui, confirm=args.confirm)
    print(result.to_markdown())
    return 0 if result.success else 1


def _cmd_wait_download(args: argparse.Namespace) -> int:
    """Wait for a browser download to complete and print its path (Phase 5)."""
    from desktop_worker.workflows import get_downloads_dir, wait_for_download

    directory = args.dir or get_downloads_dir()
    print(f"Watching {directory} for a new completed download (timeout {args.timeout}s) ...")
    path = wait_for_download(directory, timeout_s=args.timeout)
    if path is None:
        print(f"No new download appeared within {args.timeout}s.")
        return 1
    print(f"Downloaded: {path}")
    return 0


def _cmd_browse(args: argparse.Namespace) -> int:
    """Open Chrome, navigate to a URL, and optionally fill + submit a form (Phase 5)."""
    import time

    from desktop_worker.workflows import navigate, open_chrome, submit_form
    from desktop_worker.workflows.browser_ui import get_browser_ui

    real = not args.null
    cfg = Config(session_id="workflow", task_id="browse")
    session = Session(cfg, prefer_real_backends=real)
    ui = get_browser_ui(prefer_real=real)
    cwd = str(cfg.artifacts_root.parent)

    fields: dict[str, str] = {}
    for pair in args.fill or []:
        if "=" not in pair:
            print(f"--fill expects label=value, got {pair!r}")
            return 2
        k, v = pair.split("=", 1)
        fields[k.strip()] = v

    if real:
        r = open_chrome(broker=session.broker, cwd=cwd)
        print(r.to_markdown())
        if not r.success:
            return 1
        time.sleep(3.0)

    if fields:
        result = submit_form(fields, executor=session.executor, ui=ui, url=args.url,
                             submit_label=args.submit)
    else:
        result = navigate(args.url, executor=session.executor)
    print(result.to_markdown())
    return 0 if result.success else 1


def _live_implement(task, *, session, cwd):
    """Run one orchestration task live (gated by --execute). Returns an AgentReport.

    Builds a minimal Claude-driven loop for the task goal and maps the TaskReport
    onto an AgentReport. This is the only side-effecting path and runs only under
    an explicit opt-in; the deterministic coordinator/state-machine is unaffected.
    """
    from desktop_worker.config import Limits
    from desktop_worker.loop.claude_cli_planner import ClaudeCliPlanner
    from desktop_worker.loop.task_loop import TaskLoop
    from desktop_worker.orchestration import AgentReport
    from desktop_worker.perception import Perceiver, get_ocr_backend, get_uia_backend

    planner = ClaudeCliPlanner(task=task.goal, broker=session.broker, cwd=cwd,
                               audit=session.audit)
    perceiver = Perceiver(ocr=get_ocr_backend(True), uia=get_uia_backend(True))
    loop = TaskLoop(task_id=f"orch-{task.id}", planner=planner, observer=session.observer,
                    executor=session.executor, audit=session.audit, estop=session.estop,
                    perceiver=perceiver, settle_s=0.5, stall_guard=True,
                    limits=Limits(max_actions_per_task=15, max_task_seconds=180))
    report = loop.run()
    status = "done" if report.completed else "failed"
    return AgentReport(task_id=task.id, status=status,
                       summary=planner.last_done_reason or f"{report.steps_run} steps",
                       evidence=[f"{report.steps_run} steps", f"stop={report.stop_reason}"])


def _cmd_orchestrate(args: argparse.Namespace) -> int:
    """Decompose a goal and run it through the multi-agent pipeline (Phase 6).

    Plan-only by default (Strategist + auditors propose; no desktop side effects).
    Pass --execute to let the Implementer actually drive the desktop per task.
    """
    from desktop_worker.orchestration import (CodexAuditor, Coordinator, Implementer,
                                              NorthstarAuditor, Strategist)
    from desktop_worker.orchestration.claude_io import make_role_ask
    from desktop_worker.loop.claude_cli_planner import claude_available

    real = not args.null
    cfg = Config(session_id="orchestrate", task_id="task")
    session = Session(cfg, prefer_real_backends=real)
    cwd = str(cfg.artifacts_root.parent)
    broker = session.broker

    if real and not claude_available(broker, cwd):
        print("ERROR: the `claude` CLI is not logged in. Run `claude auth status`.")
        return 2

    # --null runs fully offline (like `demo`): canned role responses, no claude.
    _OFFLINE = {
        "strategist": '[{"id": "T1", "goal": "%(g)s (step 1)"}, '
                      '{"id": "T2", "goal": "%(g)s (step 2)"}]',
        "implementer": '{"taskId": "T1", "status": "done", "summary": "offline demo"}',
        "codex_auditor": '{"severity": "low", "verdict": "approve", "message": "demo"}',
        "northstar_auditor": '{"severity": "low", "verdict": "approve", "message": "demo"}',
    }

    def ask_for(agent, role):
        if not real:
            canned = _OFFLINE.get(role, "{}") % {"g": args.goal}
            return lambda _prompt: canned
        return make_role_ask(broker, cwd, agent=agent, role=role)

    strategist = Strategist(ask=ask_for("Strategist", "strategist"), audit=session.audit)
    if args.execute:
        print("EXECUTE mode: the Implementer will drive the real desktop per task.")
        implementer = Implementer(
            execute_fn=lambda t: _live_implement(t, session=session, cwd=cwd),
            audit=session.audit)
    else:
        implementer = Implementer(ask=ask_for("Implementer", "implementer"),
                                  audit=session.audit)
    codex = CodexAuditor(ask=ask_for("Codex Auditor", "codex_auditor"), audit=session.audit)
    northstar = NorthstarAuditor(ask=ask_for("Northstar Auditor", "northstar_auditor"),
                                 audit=session.audit)

    coord = Coordinator(strategist=strategist, implementer=implementer,
                        codex=codex, northstar=northstar, audit=session.audit)
    print(f"GOAL: {args.goal}\n(plan-only)" if not args.execute else f"GOAL: {args.goal}")
    result = coord.run(args.goal)
    print(result.to_markdown())
    print(f"Audit log: {cfg.audit_file}")
    return 0 if (result.outcomes and result.blocked == 0) else 1


def _console_approver(request) -> bool:
    """Interactive approval for high-risk actions; deny if not a TTY (headless)."""
    try:
        if not sys.stdin or not sys.stdin.isatty():
            return False
        print(f"\n[APPROVAL NEEDED] risk={request.risk.value} :: {request.summary}")
        return input("  Allow this action? [y/N] ").strip().lower() in ("y", "yes")
    except Exception:
        return False


def _cmd_draw(args: argparse.Namespace) -> int:
    """Draw a recognizable figure of <subject> in Paint — best-of-N + AI judge.

    The AI proposes several SVG drawings; we render them offline, an AI judge picks
    the best, and ONLY the winner is drawn — on a freshly cleaned canvas with the
    Pencil + black selected. No raw mouse strokes are ever emitted, so the canvas
    cannot be scribbled over. ~3-4 Claude calls total (quota-friendly).
    """
    import time

    from desktop_worker.drawing import DrawingDirector
    from desktop_worker.drawing.claude_io import make_claude_callers
    from desktop_worker.geometry import get_canvas_locator
    from desktop_worker.geometry.paint_setup import get_paint_ui
    from desktop_worker.loop.claude_cli_planner import claude_available
    from desktop_worker.tools.builtin import render_program_to_canvas

    real = not args.null
    cfg = Config(session_id="ai-draw", task_id="task")
    session = Session(cfg, prefer_real_backends=real)
    cwd = str(cfg.artifacts_root.parent)
    if real and not claude_available(session.broker, cwd):
        print("ERROR: the `claude` CLI is not logged in. Run `claude auth status`.")
        return 2

    work = cfg.task_dir / "draw"
    work.mkdir(parents=True, exist_ok=True)

    # Make sure Paint is open (the prep step focuses/maximizes it before drawing).
    if real:
        session.broker.launch('start "" mspaint', cwd, agent="draw", role="tool")
        time.sleep(3.0)

    locator = get_canvas_locator(real)
    paint_ui = get_paint_ui(real)

    def draw_fn(program):
        return render_program_to_canvas(
            program, input_backend=session.input_backend, canvas_locator=locator,
            estop=session.estop, paint_ui=paint_ui, clear=True)

    def screenshot_fn():
        dest = work / "canvas.png"
        try:
            return session.desktop_backend.capture_screenshot(dest)
        except Exception:
            return None

    ask_text, ask_vision = make_claude_callers(session.broker, cwd)
    director = DrawingDirector(
        ask_text=ask_text, ask_vision=ask_vision, draw_fn=draw_fn,
        work_dir=str(work), screenshot_fn=screenshot_fn,
        n_candidates=args.candidates, refine=not args.no_refine,
        log=lambda m: print(f"[draw] {m}"))

    print(f"Drawing '{args.subject}' (best-of-{args.candidates}). "
          "This makes a few Claude calls (your subscription). Press estop to stop.")
    res = director.draw(args.subject)
    if res.get("success"):
        print(f"Done: chose candidate #{res['chosen']} of {res['candidates']}"
              + (f", refined once ({res['verdict'].get('issue')})" if res.get("refined") else "")
              + f"; drew {res['draw'].get('strokes')} strokes. "
              f"Canvas source: {res['draw'].get('canvasSource')}.")
        return 0
    print(f"Could not draw: {res.get('error')}")
    return 1


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
    from desktop_worker.safety import build_policy

    real = not args.null
    cfg = Config(session_id="ai-do", task_id="task")
    # Permission profile (requirements §12): standard (low/med auto, high prompts),
    # strict (medium+ prompts), or headless (deny anything needing approval).
    policy = build_policy(args.profile, _console_approver)
    if args.profile != "standard":
        print(f"Permission profile: {args.profile}.")
    session = Session(cfg, policy=policy, prefer_real_backends=real)

    cwd = str(cfg.artifacts_root.parent)
    if real and not claude_available(session.broker, cwd):
        print("ERROR: the `claude` CLI is not logged in. Run `claude auth status`.")
        return 2

    from desktop_worker.workflows.desktop_ui import get_desktop_dir, get_desktop_ui

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
        "choose New then Text Document; menu items appear as elements to click by id.\n"
        "- To DRAW a figure in Paint, do NOT emit raw mouse strokes. Open Paint first "
        "(open_app 'paint'); make sure a drawing tool (Pencil or Brush) is selected — "
        "click it by elementId if you just used Select/clear, else the default brush is "
        "fine. Then call the `sketch` tool ONCE with the WHOLE figure as a "
        "list of geometric primitives on a 0..100 grid (x and y both 0..100, origin "
        "top-left), OR an `svg` string (viewBox 0 0 100 100, black stroke, paths/circles/"
        "etc.) — the sketch tool clears the canvas and picks the Pencil first. The app "
        "finds Paint's real canvas and renders precisely — circles are "
        "true circles, curves are smooth, no stray lines. Think on the grid, e.g. a cat: "
        "head circle center [50,40] r 22; two triangular ears as closed polylines; eyes "
        "as small circles ~[42,38]/[58,38] r 3; nose as a dot [50,46]; mouth as an arc "
        "center [50,47] r 8 start 20 end 160; whiskers as lines; body ellipse [50,72]; "
        "tail as a bezier. Primitive kinds: line{from,to}, polyline{points,closed?}, "
        "circle{center,r}, ellipse{center,rx,ry,rotation?}, arc{center,r,start,end}, "
        "bezier{points: 3=quadratic or 4=cubic}, dot{at}. After drawing you get ONE "
        "cropped look at the canvas (with --vision) to critique and ONE optional "
        "correction sketch — so make the first program complete."
    )
    # Reliable tools the AI may CHOOSE to call ("brain + hands"). The tool runs
    # through the same audited/estop-gated executor for each of its sub-actions.
    from desktop_worker.geometry import get_canvas_locator
    from desktop_worker.geometry.paint_setup import get_paint_ui
    from desktop_worker.tools import (CreateTextFileTool, DragDropTool, FocusWindowTool,
                                      OpenAppTool, OpenUrlTool, SketchTool, ToolRegistry)

    tools = ToolRegistry()
    tools.register(CreateTextFileTool(desktop_dir=desktop_dir, broker=session.broker))
    tools.register(OpenAppTool(desktop_dir=desktop_dir, broker=session.broker))
    tools.register(OpenUrlTool(desktop_dir=desktop_dir, broker=session.broker))
    tools.register(FocusWindowTool())
    tools.register(DragDropTool(input_backend=session.input_backend, estop=session.estop))
    tools.register(SketchTool(input_backend=session.input_backend,
                              canvas_locator=get_canvas_locator(real),
                              estop=session.estop, paint_ui=get_paint_ui(real)))
    session.executor.tools = tools

    perceiver = Perceiver(ocr=get_ocr_backend(real), uia=get_uia_backend(real))
    planner = ClaudeCliPlanner(task=args.task, broker=session.broker, cwd=cwd,
                               audit=session.audit, env_context=env_context,
                               vision=args.vision, tools_catalog=tools.catalog(),
                               frugal=args.frugal)
    if args.frugal:
        print("Frugal mode ON: leaner prompts (fewer elements/history) to use less "
              "Claude usage per step — the AI sees fewer on-screen elements, so on busy "
              "screens it may miss a target (reliability vs cost trade-off).")
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
    # Auto-generate a human-readable HTML replay (best-effort: never let replay
    # generation mask the actual task outcome).
    try:
        from desktop_worker.audit.report import write_html_report
        replay = write_html_report(cfg.audit_file, cfg.task_dir / "replay.html",
                                   title=f"do: {args.task}")
        print(f"Replay (open in browser): {replay}")
    except Exception as exc:  # noqa: BLE001
        print(f"(replay generation skipped: {exc})")
    return 0 if report.completed else 1


def _cmd_report(args: argparse.Namespace) -> int:
    """Build an HTML replay from a session/task's audit log."""
    from desktop_worker.audit.report import write_html_report

    cfg = Config(session_id=args.session, task_id=args.task)
    if not cfg.audit_file.exists():
        print(f"No audit log at {cfg.audit_file}")
        return 1
    out = write_html_report(cfg.audit_file, cfg.task_dir / "replay.html",
                            title=f"{args.session}/{args.task}")
    print(f"Replay written: {out}")
    return 0


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

    sw = sub.add_parser("switch-window",
                        help="bring an open window to the front by (part of) its title")
    sw.add_argument("title", help="text appearing in the target window's title")
    sw.set_defaults(func=_cmd_switch_window)

    pf = sub.add_parser("pick-file",
                        help="fill an already-open native file dialog with a path and confirm")
    pf.add_argument("path", help="the file path to type into the dialog")
    pf.add_argument("--confirm", choices=("open", "save"), default="open",
                    help="which confirm button to click (open=file picker/upload, save=save-as)")
    pf.set_defaults(func=_cmd_pick_file)

    wd = sub.add_parser("wait-download",
                        help="wait for a browser download to finish and print its path")
    wd.add_argument("--dir", default=None, help="download directory (default: ~/Downloads)")
    wd.add_argument("--timeout", type=float, default=60.0, help="max seconds to wait")
    wd.set_defaults(func=_cmd_wait_download)

    br = sub.add_parser("browse",
                        help="open Chrome, navigate to a URL, optionally fill + submit a form")
    br.add_argument("url", help="the http(s) URL to navigate to")
    br.add_argument("--fill", action="append", metavar="LABEL=VALUE",
                    help="fill an input by (part of) its label; repeatable")
    br.add_argument("--submit", default=None, help="name of the submit button to click")
    br.set_defaults(func=_cmd_browse)

    orc = sub.add_parser("orchestrate",
                         help="decompose a goal and run it through the multi-agent pipeline")
    orc.add_argument("goal", help="the high-level goal in plain language")
    orc.add_argument("--execute", action="store_true",
                     help="let the Implementer drive the real desktop (default: plan-only)")
    orc.set_defaults(func=_cmd_orchestrate)

    do = sub.add_parser("do", help="give a natural-language task; the AI drives it live")
    do.add_argument("task", help="the task in plain language, e.g. \"open Notepad and type hi\"")
    do.add_argument("--max-actions", type=int, default=15, help="max actions before stopping")
    do.add_argument("--max-seconds", type=int, default=300, help="max task time")
    do.add_argument("--vision", action="store_true",
                    help="let Claude SEE a screenshot when accessibility data is sparse "
                         "(works on more apps; costs more Claude usage)")
    do.add_argument("--frugal", action="store_true",
                    help="leaner prompts (fewer elements/history) to use less Claude "
                         "usage per step")
    do.add_argument("--profile", choices=("standard", "strict", "headless"),
                    default="standard",
                    help="permission profile: standard (low/med auto, high prompts), "
                         "strict (medium+ prompts), headless (deny anything needing approval)")
    do.set_defaults(func=_cmd_do)

    dr = sub.add_parser("draw", help="draw a recognizable figure of <subject> in Paint "
                                     "(best-of-N candidates + AI judge, clean execution)")
    dr.add_argument("subject", help='what to draw, e.g. "a cat", "a house", "a smiling sun"')
    dr.add_argument("--candidates", type=int, default=3,
                    help="how many candidate drawings the AI proposes (judge picks the best)")
    dr.add_argument("--no-refine", action="store_true",
                    help="skip the one-shot verify+correct pass (fewer Claude calls)")
    dr.set_defaults(func=_cmd_draw)

    rep = sub.add_parser("report", help="build an HTML replay of a session's audit log")
    rep.add_argument("--session", default="ai-do", help="session id")
    rep.add_argument("--task", default="task", help="task id")
    rep.set_defaults(func=_cmd_report)
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
