"""Smoke tests for the Tkinter UI module + CLI wiring (Phase 7).

The GUI itself is validated manually (MANUAL-UI-1). Here we only assert the
module imports without a display (tkinter is imported lazily) and that the `ui`
command is wired into the parser.
"""

import desktop_worker.ui.app_tk as app_tk
from desktop_worker.__main__ import build_parser


def test_app_tk_imports_without_display():
    # tkinter must NOT be imported at module load (no display on CI).
    assert callable(app_tk.run_control_window)


def test_ui_command_registered():
    parser = build_parser()
    # argparse exposes subparser choices via the subparsers action.
    sub = [a for a in parser._actions if hasattr(a, "choices") and a.choices]
    names = set()
    for a in sub:
        names.update(a.choices.keys())
    assert "ui" in names
    assert "orchestrate" in names
    assert "clean-artifacts" in names


def test_run_control_window_signature():
    import inspect
    params = inspect.signature(app_tk.run_control_window).parameters
    assert "controller" in params and "run_task" in params
