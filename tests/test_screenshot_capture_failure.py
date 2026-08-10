"""Screenshot capture failures must surface a machine-readable reason —
never a silent ok=true / path=null (UQC-BL-1).

capture_screenshot() returning None used to mean two different, un-tellable-
apart things: "no screenshot was requested" and "the capture failed" (most
commonly: the ``mss`` dependency is not installed in the interpreter that
spawned the headless MCP server). These tests pin the fix at each layer:
the Windows backend records *why* on ``last_screenshot_error``, the Observer
carries it onto the Observation, and (see test_mcp_bridge.py) the MCP
bridge's screenshot tool reports ok=False with a reason instead of ok=True
with path=None.
"""

import builtins

import pytest

from desktop_worker.observation.backends import NullDesktopBackend
from desktop_worker.observation.observer import Observer


def _hide(monkeypatch, *modules):
    real_import = builtins.__import__

    def fake(name, *a, **k):
        if name in modules or name.split(".")[0] in modules:
            raise ImportError(f"hidden for test: {name}")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)


def test_missing_mss_reports_a_machine_readable_reason_not_silent_none(monkeypatch, tmp_path):
    from desktop_worker.observation.windows_backend import WindowsDesktopBackend

    backend = WindowsDesktopBackend()
    _hide(monkeypatch, "mss")

    ref = backend.capture_screenshot(tmp_path / "shot.png")

    assert ref is None
    assert backend.last_screenshot_error is not None
    assert "missing_dependency" in backend.last_screenshot_error
    assert "mss" in backend.last_screenshot_error


def test_capture_error_after_import_succeeds_is_also_reported(monkeypatch, tmp_path):
    pytest.importorskip("mss")
    import mss

    from desktop_worker.observation.windows_backend import WindowsDesktopBackend

    backend = WindowsDesktopBackend()

    def boom(*a, **k):
        raise RuntimeError("simulated grab failure")

    monkeypatch.setattr(mss, "mss", boom)

    ref = backend.capture_screenshot(tmp_path / "shot.png")

    assert ref is None
    assert backend.last_screenshot_error is not None
    assert backend.last_screenshot_error.startswith("capture_failed")
    assert "simulated grab failure" in backend.last_screenshot_error


def test_null_backend_never_reports_a_screenshot_error(tmp_path):
    backend = NullDesktopBackend()
    ref = backend.capture_screenshot(tmp_path / "shot.png")
    assert ref is not None
    assert backend.last_screenshot_error is None


class _FailingBackend(NullDesktopBackend):
    """A desktop backend whose screenshot capture always fails, with a reason."""

    def capture_screenshot(self, dest):
        self.last_screenshot_error = "missing_dependency: ModuleNotFoundError: mss"
        return None


def test_observer_carries_the_backend_failure_reason_onto_the_observation(tmp_path):
    backend = _FailingBackend()
    obs = Observer(backend, screenshots_dir=tmp_path / "shots").observe("t")

    assert obs.screenshotRef is None
    assert obs.screenshotError == "missing_dependency: ModuleNotFoundError: mss"
    assert obs.to_dict()["screenshotError"] == obs.screenshotError


def test_observer_leaves_error_none_when_screenshot_not_requested(tmp_path):
    backend = _FailingBackend()
    obs = Observer(backend, screenshots_dir=tmp_path / "shots").observe("t", screenshot=False)

    assert obs.screenshotRef is None
    assert obs.screenshotError is None


def test_observer_reports_a_generic_reason_if_the_backend_gives_none(tmp_path):
    """A backend that returns None without setting last_screenshot_error still
    must not leave the failure unexplained."""

    class _SilentFailingBackend(NullDesktopBackend):
        def capture_screenshot(self, dest):
            return None

    obs = Observer(_SilentFailingBackend(), screenshots_dir=tmp_path / "shots").observe("t")
    assert obs.screenshotRef is None
    assert obs.screenshotError
