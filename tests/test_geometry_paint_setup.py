"""Tests for canvas hygiene orchestration (prepare_paint)."""

from desktop_worker.actions.backends import NullInputBackend
from desktop_worker.geometry.paint_setup import NullPaintUi, get_paint_ui, prepare_paint


class FakePaintUi:
    """Records and answers find/focus so prepare_paint is fully testable."""

    def __init__(self, focused=True, tools=None, colors=None):
        self._focused = focused
        self._tools = {"Pencil": (326, 111), "Brushes": (504, 135)} if tools is None else tools
        self._colors = {"Black": (470, 55)} if colors is None else colors

    def focus(self):
        return self._focused

    def tool_center(self, name):
        return self._tools.get(name)

    def color_center(self, name):
        return self._colors.get(name)


def test_prepare_paint_clears_selects_tool_and_color():
    ib = NullInputBackend()
    res = prepare_paint(ib, FakePaintUi(), clear=True, tool="Pencil", color="Black")
    assert res == {"focused": True, "cleared": True, "tool": "Pencil", "color": "Black"}
    names = [c[0] for c in ib.calls]
    # clears (Ctrl+A, Delete, Escape) THEN clicks the tool + colour.
    assert names == ["hotkey", "press_key", "press_key", "click", "click"]
    assert ib.calls[0] == ("hotkey", ("CTRL", "A"))
    assert ("click", "left", 326, 111) in ib.calls       # Pencil
    assert ("click", "left", 470, 55) in ib.calls        # Black


def test_prepare_paint_missing_tool_reports_none_and_no_click():
    ib = NullInputBackend()
    res = prepare_paint(ib, FakePaintUi(tools={}), clear=False, tool="Pencil", color=None)
    assert res["tool"] is None and res["cleared"] is False and res["focused"] is True
    assert not any(c[0] == "click" for c in ib.calls)    # nothing to click


def test_prepare_paint_with_null_ui_is_safe():
    ib = NullInputBackend()
    res = prepare_paint(ib, NullPaintUi(), clear=True, tool="Pencil")
    assert res["focused"] is False and res["tool"] is None
    # still issues the clear keystrokes (harmless on any app)
    assert ("hotkey", ("CTRL", "A")) in ib.calls


def test_factory_returns_null_when_not_real():
    assert isinstance(get_paint_ui(prefer_real=False), NullPaintUi)
