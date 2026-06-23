"""Tests for the native file-picker (Open/Save dialog) workflow (Phase 5)."""

from desktop_worker.actions.backends import NullInputBackend
from desktop_worker.actions.executor import ActionExecutor
from desktop_worker.audit.log import AuditLog
from desktop_worker.safety.emergency_stop import EmergencyStop
from desktop_worker.safety.policy import PermissionPolicy, auto_approve
from desktop_worker.workflows import choose_file, upload_file
from desktop_worker.workflows.file_dialog import (
    NullFileDialogUi,
    OPEN_BUTTON_NAMES,
    SAVE_BUTTON_NAMES,
    get_file_dialog_ui,
)


class FakeFileDialogUi:
    """Returns fixed coords; records which button name set was requested."""

    def __init__(self, edit=(100, 50), button=(200, 80)):
        self._edit = edit
        self._button = button
        self.button_names = None

    def file_name_edit_center(self, names=None, timeout=2.0):
        return self._edit

    def button_center(self, names, timeout=2.0):
        self.button_names = names
        return self._button


def _executor(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    policy = PermissionPolicy(approval_callback=auto_approve)
    ib = NullInputBackend()
    ex = ActionExecutor(audit=audit, policy=policy, input_backend=ib,
                        estop=EmergencyStop())
    return ex, ib


def test_choose_file_types_path_and_clicks_open(tmp_path):
    ex, ib = _executor(tmp_path)
    ui = FakeFileDialogUi(edit=(100, 50), button=(200, 80))
    res = choose_file(r"C:\docs\report.pdf", executor=ex, ui=ui,
                      confirm="open", sleep=lambda s: None)
    assert res.success
    names = [c[0] for c in ib.calls]
    assert "click" in names and "type_text" in names
    assert ("type_text", r"C:\docs\report.pdf") in ib.calls
    # clicked the edit, then the open button
    clicks = [c for c in ib.calls if c[0] == "click"]
    assert (100, 50) == (clicks[0][2], clicks[0][3])
    assert (200, 80) == (clicks[1][2], clicks[1][3])
    assert ui.button_names == OPEN_BUTTON_NAMES


def test_choose_file_save_uses_save_button(tmp_path):
    ex, ib = _executor(tmp_path)
    ui = FakeFileDialogUi()
    res = choose_file("out.txt", executor=ex, ui=ui, confirm="save", sleep=lambda s: None)
    assert res.success
    assert ui.button_names == SAVE_BUTTON_NAMES


def test_choose_file_falls_back_to_enter_when_no_button(tmp_path):
    ex, ib = _executor(tmp_path)

    class NoButtonUi(FakeFileDialogUi):
        def button_center(self, names, timeout=2.0):
            return None

    res = choose_file("x.txt", executor=ex, ui=NoButtonUi(), sleep=lambda s: None)
    assert res.success
    assert ("press_key", "ENTER") in ib.calls


def test_choose_file_no_edit_field_fails_safe(tmp_path):
    ex, ib = _executor(tmp_path)
    res = choose_file("x.txt", executor=ex, ui=NullFileDialogUi(), sleep=lambda s: None)
    assert not res.success
    assert "File name" in res.error
    assert ib.calls == []  # nothing typed/clicked


def test_choose_file_empty_path_fails(tmp_path):
    ex, ib = _executor(tmp_path)
    res = choose_file("   ", executor=ex, ui=FakeFileDialogUi(), sleep=lambda s: None)
    assert not res.success
    assert "empty" in res.error


def test_upload_file_delegates_to_open(tmp_path):
    ex, ib = _executor(tmp_path)
    ui = FakeFileDialogUi()
    res = upload_file(r"C:\f.png", executor=ex, ui=ui, sleep=lambda s: None)
    assert res.success
    assert ui.button_names == OPEN_BUTTON_NAMES


def test_factory_falls_back_to_null_without_windows():
    # On CI/non-Windows (or without uiautomation) the factory returns the Null UI.
    ui = get_file_dialog_ui(prefer_real=False)
    assert isinstance(ui, NullFileDialogUi)
