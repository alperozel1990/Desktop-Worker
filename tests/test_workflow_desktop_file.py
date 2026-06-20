"""Tests for the create-desktop-file workflow (Phase 5).

The real GUI run is validated manually (MANUAL-8); here we test the pure path
logic, safe-failure when targets can't be located, and the on-disk verification
+ step orchestration with fakes (no real desktop, instant).
"""

from pathlib import Path

from desktop_worker.schema.actions import parse_action
from desktop_worker.schema.results import ActionResult
from desktop_worker.util import utc_now_iso
from desktop_worker.workflows.desktop_file import (
    create_desktop_text_file,
    desktop_file_path,
)
from desktop_worker.workflows.desktop_ui import NullDesktopUi


class FakeExecutor:
    """Records executed actions; always succeeds. Validates each action dict."""

    def __init__(self):
        self.types = []

    def execute(self, action):
        # action is already a validated Action (parse_action ran in the workflow)
        self.types.append(action.type)
        now = utc_now_iso()
        return ActionResult(action_type=action.type, success=True, startedAt=now, endedAt=now)


class FakeUi:
    """Locates everything at fixed points; reports the editor ready."""

    def __init__(self, filename="dw-demo"):
        self._title = f"{filename}.txt - Notepad"

    def show_desktop(self): return True
    def menu_item_center(self, names, timeout=2.0): return (10, 10)
    def desktop_item_center(self, names, timeout=2.0): return (20, 20)
    def active_window_title(self): return self._title


_NOSLEEP = lambda *_: None


def test_desktop_file_path_adds_txt():
    assert desktop_file_path("C:/Desktop", "dw-demo").endswith("dw-demo.txt")
    assert desktop_file_path("C:/Desktop", "note.txt").endswith("note.txt")
    # no double extension
    assert desktop_file_path("C:/Desktop", "note.txt").count(".txt") == 1


def test_happy_path_succeeds_and_verifies(tmp_path):
    # Pre-create the file as the GUI would have, so on-disk verification passes.
    (tmp_path / "dw-demo.txt").write_text("başlıyoruz", encoding="utf-8")
    res = create_desktop_text_file(
        "başlıyoruz", executor=FakeExecutor(), ui=FakeUi(),
        desktop_dir=str(tmp_path), screen_size=(1920, 1080),
        filename="dw-demo", sleep=_NOSLEEP,
    )
    assert res.success is True
    assert res.error == ""
    assert "verified content on disk" in res.steps[-1]


def test_emits_expected_structured_actions(tmp_path):
    (tmp_path / "dw-demo.txt").write_text("başlıyoruz", encoding="utf-8")
    ex = FakeExecutor()
    create_desktop_text_file(
        "başlıyoruz", executor=ex, ui=FakeUi(),
        desktop_dir=str(tmp_path), screen_size=(1920, 1080), sleep=_NOSLEEP,
    )
    # The visible sequence the user asked for, as structured actions:
    assert "mouse.rightClick" in ex.types          # right-click desktop
    assert ex.types.count("mouse.click") >= 2      # New + Text Document
    assert "mouse.doubleClick" in ex.types         # open the file
    assert "keyboard.type" in ex.types             # name + content
    assert "keyboard.hotkey" in ex.types           # Ctrl+S


def test_fails_safe_when_menu_not_found(tmp_path):
    res = create_desktop_text_file(
        "başlıyoruz", executor=FakeExecutor(), ui=NullDesktopUi(),
        desktop_dir=str(tmp_path), screen_size=(1920, 1080), sleep=_NOSLEEP,
    )
    assert res.success is False
    assert "New" in res.error                      # clear, specific failure
    assert not (tmp_path / "dw-demo.txt").exists()  # nothing fabricated


def test_fails_when_content_not_on_disk(tmp_path):
    # FakeUi locates everything and executor "succeeds", but no file is written,
    # so verification must fail (workflow never lies about success).
    res = create_desktop_text_file(
        "başlıyoruz", executor=FakeExecutor(), ui=FakeUi(),
        desktop_dir=str(tmp_path), screen_size=(1920, 1080), sleep=_NOSLEEP,
    )
    assert res.success is False
    assert "did not contain expected content" in res.error
