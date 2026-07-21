"""Tests for the deterministic eval oracles (Phase 10).

An oracle that is wrong is worse than no oracle — it turns a broken system into a
green bar. These tests pin down both directions: an oracle must pass when the
state is right AND fail when it is wrong, with a reason that says why.
"""

import pytest

from desktop_worker.eval.oracles import (
    AllOf,
    AnyOf,
    ClipboardEquals,
    ElementPresent,
    FileContains,
    FileExists,
    ProbeFlag,
    ReportedInfeasible,
    StateChanged,
    Verdict,
    WindowTitleMatches,
)


class FakeBridge:
    """Minimal bridge stand-in: returns whatever the test dictates."""

    def __init__(self, *, title="", clipboard="", elements=None):
        self._title = title
        self._clipboard = clipboard
        self._elements = elements or []

    def observe(self, screenshot=True):
        return {"ok": True, "observation": {"activeWindow": {"title": self._title}}}

    def perceive(self, screenshot=True):
        return {"ok": True, "elements": self._elements, "activeWindow": {"title": self._title}}

    def clipboard_get(self):
        return {"ok": True, "detail": {"text": self._clipboard}}


class Ctx:
    def __init__(self, bridge):
        self.bridge = bridge


# -- file oracles ----------------------------------------------------------


def test_file_exists_both_directions(tmp_path):
    target = tmp_path / "made.txt"
    ctx = Ctx(FakeBridge())

    missing = FileExists(target).check(ctx, {})
    assert missing.passed is False
    assert "does not exist" in missing.reason

    target.write_text("hi", encoding="utf-8")
    found = FileExists(target).check(ctx, {})
    assert found.passed is True


def test_file_contains_distinguishes_missing_from_wrong_content(tmp_path):
    target = tmp_path / "note.txt"
    ctx = Ctx(FakeBridge())

    absent = FileContains(target, "needle").check(ctx, {})
    assert absent.passed is False
    assert "does not exist" in absent.reason

    target.write_text("haystack only", encoding="utf-8")
    wrong = FileContains(target, "needle").check(ctx, {})
    assert wrong.passed is False
    assert "does not contain" in wrong.reason

    target.write_text("has a needle inside", encoding="utf-8")
    assert FileContains(target, "needle").check(ctx, {}).passed is True


# -- desktop-state oracles -------------------------------------------------


def test_window_title_matches_is_regex_and_case_insensitive():
    ctx = Ctx(FakeBridge(title="Untitled - Notepad"))
    assert WindowTitleMatches(r"notepad").check(ctx, {}).passed is True
    assert WindowTitleMatches(r"Notepad|Not Defteri").check(ctx, {}).passed is True

    verdict = WindowTitleMatches(r"Blender").check(ctx, {})
    assert verdict.passed is False
    assert "Untitled - Notepad" in verdict.reason


def test_clipboard_equals_reports_what_it_actually_found():
    ctx = Ctx(FakeBridge(clipboard="actual"))
    verdict = ClipboardEquals("expected").check(ctx, {})
    assert verdict.passed is False
    assert "'actual'" in verdict.reason
    assert ClipboardEquals("actual").check(ctx, {}).passed is True


def test_element_present_matches_on_text_or_type():
    elements = [
        {"id": "uia-1", "type": "button", "text": "Save", "label": ""},
        {"id": "uia-2", "type": "edit", "text": "", "label": "Text editor"},
    ]
    ctx = Ctx(FakeBridge(elements=elements))

    assert ElementPresent(text="save").check(ctx, {}).passed is True
    assert ElementPresent(control_type="edit").check(ctx, {}).passed is True
    assert ElementPresent(text="Save", control_type="button").check(ctx, {}).passed is True
    # text present but wrong type => no match
    assert ElementPresent(text="Save", control_type="edit").check(ctx, {}).passed is False
    assert ElementPresent(text="Publish").check(ctx, {}).passed is False


def test_element_present_prefers_payload_elements_over_a_second_perceive():
    """The oracle must grade the SAME observation the probe measured."""
    bridge = FakeBridge(elements=[{"type": "button", "text": "FromBridge", "label": ""}])
    ctx = Ctx(bridge)
    payload = {"elements": [{"type": "button", "text": "FromPayload", "label": ""}]}

    assert ElementPresent(text="FromPayload").check(ctx, payload).passed is True
    assert ElementPresent(text="FromBridge").check(ctx, payload).passed is False


def test_element_present_requires_a_criterion():
    with pytest.raises(ValueError):
        ElementPresent()


def test_state_changed_both_polarities():
    ctx = Ctx(FakeBridge())
    changed = {"signatureBefore": "a", "signatureAfter": "b"}
    same = {"signatureBefore": "a", "signatureAfter": "a"}

    assert StateChanged(expect_change=True).check(ctx, changed).passed is True
    assert StateChanged(expect_change=True).check(ctx, same).passed is False
    assert StateChanged(expect_change=False).check(ctx, same).passed is True
    assert StateChanged(expect_change=False).check(ctx, changed).passed is False


def test_state_changed_fails_loudly_when_probe_recorded_nothing():
    """Missing signatures must FAIL, not silently pass."""
    verdict = StateChanged().check(Ctx(FakeBridge()), {})
    assert verdict.passed is False
    assert "did not record" in verdict.reason


# -- probe / infeasible oracles -------------------------------------------


def test_probe_flag_reads_named_flag_and_surfaces_reason():
    ctx = Ctx(FakeBridge())
    payload = {"inlineImage": False, "inlineImageReason": "no decodable image"}
    verdict = ProbeFlag("inlineImage").check(ctx, payload)
    assert verdict.passed is False
    assert "no decodable image" in verdict.reason

    assert ProbeFlag("inlineImage").check(ctx, {"inlineImage": True}).passed is True
    # expected=False inverts it
    assert ProbeFlag("inlineImage", expected=False).check(ctx, {"inlineImage": False}).passed


def test_reported_infeasible_passes_only_when_the_system_refused():
    ctx = Ctx(FakeBridge())
    assert ReportedInfeasible().check(ctx, {"ok": False}).passed is True
    assert ReportedInfeasible().check(ctx, {"refused": True}).passed is True

    claimed = ReportedInfeasible().check(ctx, {"ok": True})
    assert claimed.passed is False
    assert "claimed success" in claimed.reason


# -- composites ------------------------------------------------------------


def test_all_of_reports_every_failing_reason():
    ctx = Ctx(FakeBridge(title="Notepad"))
    oracle = AllOf(WindowTitleMatches("Notepad"), ProbeFlag("nope"))
    verdict = oracle.check(ctx, {"nope": False})
    assert verdict.passed is False
    assert "nope" in verdict.reason
    assert len(verdict.detail["checks"]) == 2


def test_all_of_passes_only_when_all_pass():
    ctx = Ctx(FakeBridge(title="Notepad"))
    assert AllOf(WindowTitleMatches("Notepad"), ProbeFlag("ok")).check(ctx, {"ok": True}).passed


def test_any_of_passes_on_first_success():
    ctx = Ctx(FakeBridge(title="Blender"))
    oracle = AnyOf(WindowTitleMatches("Notepad"), WindowTitleMatches("Blender"))
    assert oracle.check(ctx, {}).passed is True

    none = AnyOf(WindowTitleMatches("Notepad"), WindowTitleMatches("Paint")).check(ctx, {})
    assert none.passed is False


def test_composites_reject_empty_construction():
    with pytest.raises(ValueError):
        AllOf()
    with pytest.raises(ValueError):
        AnyOf()


def test_verdict_serializes():
    assert Verdict(True, "why", {"k": 1}).to_dict() == {
        "passed": True,
        "reason": "why",
        "detail": {"k": 1},
    }


# --- probe strength: positional ids must not read as "stable" ---------------
# The first live A2 run reported 100% id stability on every app, because two
# back-to-back perceives of an unchanged screen is a test a positional counter
# passes trivially. The probe now also checks structurally.


class _IdBridge:
    def __init__(self, elements):
        self._elements = elements

    def perceive(self, screenshot=True):
        return {"ok": True, "elements": self._elements}


def _ctx(elements):
    return type("C", (), {"bridge": _IdBridge(elements)})()


def test_positional_ids_are_not_reported_as_stable():
    from desktop_worker.eval.suite import probe_element_id_stable

    elements = [
        {"id": "uia-0", "type": "button", "text": "A", "label": ""},
        {"id": "uia-1", "type": "button", "text": "B", "label": ""},
    ]
    out = probe_element_id_stable(_ctx(elements))

    assert out["idsArePositional"] is True
    assert out["idsStable"] is False, "a positional counter is not a usable reference"
    assert "positional" in out["idsStableReason"]


def test_identity_bearing_ids_are_reported_as_stable():
    from desktop_worker.eval.suite import probe_element_id_stable

    elements = [
        {"id": "AutomationId:SaveBtn", "type": "button", "text": "A", "label": ""},
        {"id": "AutomationId:OpenBtn", "type": "button", "text": "B", "label": ""},
    ]
    out = probe_element_id_stable(_ctx(elements))

    assert out["idsArePositional"] is False
    assert out["idsStable"] is True
