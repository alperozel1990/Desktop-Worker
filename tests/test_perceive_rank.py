"""Tests for DW-PERCEIVE-RANK — ranking, truncation signalling and filters.

The defect being fixed: the UIA walk broke at 200 elements in tree-traversal
order with no signal. On a dense UI (Paint measured exactly 200, at cap, silently)
the control an agent needed could simply be absent, and nothing said so — the
agent could not tell "no such control" from "you were not told about it".
"""

import pytest

from desktop_worker.mcp_server.bridge import _filter_elements
from desktop_worker.perception.uia_backend import rank_and_cap, rank_key
from desktop_worker.schema.observations import Element


def _el(etype, text="t", left=0, top=0):
    return Element(
        id=f"{etype}-{left}", type=etype, bounds=(left, top, left + 10, top + 10),
        source="uia", text=text, label=text, confidence=0.99,
    )


# -- ranking ---------------------------------------------------------------


def test_interactables_outrank_static_text():
    assert rank_key(_el("button")) < rank_key(_el("text"))
    assert rank_key(_el("input")) < rank_key(_el("text"))
    assert rank_key(_el("list")) < rank_key(_el("text"))
    assert rank_key(_el("button")) < rank_key(_el("list"))


def test_truncation_keeps_actionable_controls_over_labels():
    """The whole point: if something must be dropped, drop the labels."""
    elements = [_el("text", f"label{i}", left=i) for i in range(10)]
    elements.append(_el("button", "Save", left=99))

    kept, report = rank_and_cap(elements, max_elements=3)

    assert any(e.type == "button" for e in kept), "the Save button must survive the cap"
    assert report["truncated"] is True
    assert report["dropped"] == 8


def test_ranking_is_stable_within_a_tier():
    """Traversal order is preserved among equals, so results are reproducible."""
    elements = [_el("button", f"b{i}", left=i) for i in range(5)]
    kept, _ = rank_and_cap(elements, max_elements=3)
    assert [e.text for e in kept] == ["b0", "b1", "b2"]


# -- truncation reporting --------------------------------------------------


def test_report_says_nothing_was_dropped_when_it_fits():
    elements = [_el("button", f"b{i}", left=i) for i in range(3)]
    kept, report = rank_and_cap(elements, max_elements=10)

    assert len(kept) == 3
    assert report["truncated"] is False
    assert report["dropped"] == 0
    assert report["totalSeen"] == 3


def test_report_breaks_down_what_was_dropped_by_type():
    elements = ([_el("text", f"t{i}", left=i) for i in range(5)]
                + [_el("icon", f"i{i}", left=50 + i) for i in range(3)]
                + [_el("button", "Go", left=99)])

    _kept, report = rank_and_cap(elements, max_elements=2)

    assert report["truncated"] is True
    assert report["totalSeen"] == 9
    assert report["returned"] == 2
    # icons and text are the low tiers, so they are what got cut
    assert sum(report["droppedByType"].values()) == 7


def test_empty_input_reports_cleanly():
    kept, report = rank_and_cap([], max_elements=10)
    assert kept == []
    assert report["truncated"] is False
    assert report["totalSeen"] == 0


# -- filters ---------------------------------------------------------------


def _d(etype, text, bounds):
    return {"type": etype, "text": text, "label": text, "bounds": bounds}


def test_filter_by_control_type():
    els = [_d("button", "Save", [0, 0, 10, 10]), _d("text", "Hello", [0, 0, 10, 10])]
    out = _filter_elements(els, control_type="button")
    assert [e["text"] for e in out] == ["Save"]


def test_filter_by_text_is_case_insensitive_and_matches_label():
    els = [_d("button", "Save As", [0, 0, 10, 10]), _d("button", "Cancel", [0, 0, 10, 10])]
    assert [e["text"] for e in _filter_elements(els, text_contains="save")] == ["Save As"]
    assert _filter_elements(els, text_contains="nope") == []


def test_filter_by_region_uses_element_centre():
    inside = _d("button", "In", [100, 100, 120, 120])     # centre 110,110
    outside = _d("button", "Out", [500, 500, 520, 520])   # centre 510,510
    out = _filter_elements([inside, outside], region=[0, 0, 200, 200])
    assert [e["text"] for e in out] == ["In"]


def test_filters_combine():
    els = [
        _d("button", "Save", [10, 10, 20, 20]),
        _d("text", "Save", [10, 10, 20, 20]),
        _d("button", "Save", [900, 900, 910, 910]),
    ]
    out = _filter_elements(els, control_type="button", text_contains="save",
                           region=[0, 0, 100, 100])
    assert len(out) == 1


def test_no_criteria_is_a_no_op():
    els = [_d("button", "A", [0, 0, 1, 1]), _d("text", "B", [0, 0, 1, 1])]
    assert _filter_elements(els) == els


def test_malformed_region_is_ignored_rather_than_crashing():
    els = [_d("button", "A", [0, 0, 1, 1])]
    assert _filter_elements(els, region=["x", "y", "z", "w"]) == els
    assert _filter_elements(els, region=[1, 2]) == els


def test_region_filter_drops_elements_without_usable_bounds():
    els = [{"type": "button", "text": "A", "label": "A", "bounds": None}]
    assert _filter_elements(els, region=[0, 0, 100, 100]) == []


# --- DW-ELEM-STABLE: ids must identify a control, not its position ----------
# The A2 baseline showed 100% "stable" ids on every app while ALL of them were
# `uia-<index>` — stable only because the screen was frozen. The moment the tree
# changes, a positional id points at a different control.


from desktop_worker.perception.uia_backend import stable_element_id


def _id(**kw):
    base = dict(automation_id=None, runtime_id=None, native_handle=None,
                control_type="button", name="Save", index=0)
    base.update(kw)
    return stable_element_id(**base)


def test_automation_id_wins_and_ignores_position():
    first = _id(automation_id="SaveBtn", index=0)
    later = _id(automation_id="SaveBtn", index=97)
    assert first == later
    assert first.startswith("a:")


def test_runtime_id_is_used_when_there_is_no_automation_id():
    assert _id(runtime_id=[42, 7], index=0) == _id(runtime_id=[42, 7], index=99)
    assert _id(runtime_id=[42, 7]).startswith("r:")


def test_native_handle_is_the_third_choice():
    assert _id(native_handle=12345, index=0) == _id(native_handle=12345, index=50)
    assert _id(native_handle=12345).startswith("h:")


def test_named_control_without_identity_falls_back_to_a_content_hash():
    """Still position-independent: same type+name, different walk position."""
    assert _id(name="Save", index=0) == _id(name="Save", index=31)
    assert _id(name="Save").startswith("n:")


def test_different_controls_get_different_ids():
    assert _id(name="Save") != _id(name="Cancel")
    assert _id(name="Save", control_type="button") != _id(name="Save", control_type="text")


def test_unnamed_identityless_controls_keep_the_index_as_a_last_resort():
    """Nothing distinguishes them but position — but the id says so with `n:`."""
    a = _id(name=None, index=0)
    b = _id(name=None, index=1)
    assert a != b
    assert a.startswith("n:")


def test_stronger_identity_beats_weaker_when_both_are_present():
    assert _id(automation_id="X", runtime_id=[1, 2], native_handle=9).startswith("a:")
    assert _id(runtime_id=[1, 2], native_handle=9).startswith("r:")


def test_unhashable_runtime_id_does_not_crash():
    assert _id(runtime_id=object()).startswith("r:")


def test_our_type_vocabulary_has_no_edit_type():
    """Regression: an eval task asserted control_type="edit", which cannot exist.

    control_to_type maps UIA's Edit AND Document to "input". Asserting against a
    UIA ControlType name instead of our own vocabulary made a healthy Notepad look
    broken — a measurement bug that reads exactly like a product bug.
    """
    from desktop_worker.perception.uia_backend import _CONTROL_TYPE_MAP, control_to_type

    assert "edit" not in set(_CONTROL_TYPE_MAP.values())
    assert control_to_type("EditControl") == "input"
    assert control_to_type("DocumentControl") == "input"
