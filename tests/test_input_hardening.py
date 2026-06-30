"""DW-INPUT-HARDEN — pure, testable input-planning helpers (requirements §9).

The actual SendInput calls require a live desktop (MANUAL-1); the *planning* of
key events (modifier hold/release order) and the long-text paste decision are
pure and unit-tested here.
"""

import pytest

from desktop_worker.actions.windows_input import (
    plan_hotkey,
    plan_typing,
    resolve_vk,
    should_paste,
)


def _fake_scan(ch):
    """ASCII letters/digits map to (vk, shift); everything else -> None (unicode)."""
    if ch.isascii() and (ch.isalpha() or ch.isdigit()):
        return (ord(ch.upper()), ch.isupper())
    return None


def test_plan_typing_uses_vk_for_layout_chars_unicode_otherwise():
    plan = plan_typing("Ab9€", _fake_scan)
    assert plan == [
        ("key", ord("A"), True),
        ("key", ord("B"), False),
        ("key", ord("9"), False),
        ("unicode", ord("€")),
    ]


def test_plan_typing_all_unicode_when_not_on_layout():
    plan = plan_typing("şğ", lambda ch: None)
    assert [p[0] for p in plan] == ["unicode", "unicode"]
    assert plan == [("unicode", ord("ş")), ("unicode", ord("ğ"))]


def test_plan_typing_empty():
    assert plan_typing("", _fake_scan) == []


def test_resolve_vk_known_and_aliases():
    assert resolve_vk("CTRL") == resolve_vk("CONTROL")
    assert resolve_vk("ENTER") == resolve_vk("RETURN")
    assert resolve_vk("esc") == resolve_vk("ESCAPE")   # case-insensitive
    assert resolve_vk("L") is not None


def test_resolve_vk_unknown():
    assert resolve_vk("NOPE") is None


def test_plan_hotkey_holds_then_releases_in_reverse():
    # Ctrl+L: press CTRL, press L, release L, release CTRL (modifier wraps key).
    plan = plan_hotkey(["CTRL", "L"])
    ctrl, l = resolve_vk("CTRL"), resolve_vk("L")
    assert plan == [(ctrl, "down"), (l, "down"), (l, "up"), (ctrl, "up")]


def test_plan_hotkey_three_keys():
    plan = plan_hotkey(["CTRL", "SHIFT", "ESC"])
    downs = [vk for vk, act in plan if act == "down"]
    ups = [vk for vk, act in plan if act == "up"]
    assert downs == [resolve_vk("CTRL"), resolve_vk("SHIFT"), resolve_vk("ESC")]
    assert ups == list(reversed(downs))          # released in reverse order


def test_plan_hotkey_unknown_key_raises():
    with pytest.raises(KeyError):
        plan_hotkey(["CTRL", "BOGUS"])


def test_should_paste_threshold():
    assert should_paste("short", threshold=200) is False
    assert should_paste("x" * 201, threshold=200) is True
    assert should_paste("", threshold=200) is False
