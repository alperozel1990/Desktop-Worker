"""Tests for the drawing DSL parser/validator."""

import pytest

from desktop_worker.geometry.dsl import MAX_PRIMITIVES, parse_program
from desktop_worker.tools.registry import ToolError


def test_parses_a_full_cat_program():
    prog = parse_program({"title": "cat", "primitives": [
        {"kind": "circle", "center": [50, 40], "r": 22},
        {"kind": "ellipse", "center": [50, 70], "rx": 18, "ry": 14, "rotation": 0},
        {"kind": "polyline", "points": [[33, 22], [28, 8], [42, 26]], "closed": True},
        {"kind": "arc", "center": [50, 46], "r": 8, "start": 20, "end": 160},
        {"kind": "bezier", "points": [[72, 55], [92, 60], [80, 80]]},
        {"kind": "line", "from": [30, 50], "to": [10, 47]},
        {"kind": "dot", "at": [50, 46]},
    ]})
    assert prog.title == "cat"
    assert len(prog.primitives) == 7
    assert prog.primitives[0].kind == "circle"
    assert prog.primitives[0].params["r"] == 22.0


def test_clamps_out_of_range_coordinates():
    prog = parse_program({"primitives": [{"kind": "dot", "at": [-10, 150]}]})
    assert prog.primitives[0].params["at"] == (0.0, 100.0)


def test_rejects_unknown_kind():
    with pytest.raises(ToolError):
        parse_program({"primitives": [{"kind": "spiral", "center": [1, 1], "r": 2}]})


def test_rejects_missing_fields():
    with pytest.raises(ToolError):
        parse_program({"primitives": [{"kind": "circle", "center": [50, 40]}]})  # no r
    with pytest.raises(ToolError):
        parse_program({"primitives": [{"kind": "line", "from": [1, 1]}]})        # no to


def test_rejects_non_finite_and_non_numeric():
    with pytest.raises(ToolError):
        parse_program({"primitives": [{"kind": "circle", "center": [50, 40],
                                       "r": float("inf")}]})
    with pytest.raises(ToolError):
        parse_program({"primitives": [{"kind": "dot", "at": ["x", 1]}]})
    with pytest.raises(ToolError):
        parse_program({"primitives": [{"kind": "dot", "at": [True, 1]}]})        # bool != number


def test_rejects_degenerate_arc():
    with pytest.raises(ToolError):
        parse_program({"primitives": [{"kind": "arc", "center": [50, 50], "r": 8,
                                       "start": 90, "end": 90}]})  # zero span


def test_rejects_bad_bezier_arity():
    with pytest.raises(ToolError):
        parse_program({"primitives": [{"kind": "bezier", "points": [[0, 0], [1, 1]]}]})  # 2
    with pytest.raises(ToolError):
        parse_program({"primitives": [{"kind": "bezier",
                                       "points": [[0, 0], [1, 1], [2, 2], [3, 3], [4, 4]]}]})  # 5


def test_rejects_empty_and_oversized():
    with pytest.raises(ToolError):
        parse_program({"primitives": []})
    with pytest.raises(ToolError):
        parse_program({"primitives": [{"kind": "dot", "at": [1, 1]}] * (MAX_PRIMITIVES + 1)})


def test_rejects_non_object_args_and_primitive():
    with pytest.raises(ToolError):
        parse_program("notadict")
    with pytest.raises(ToolError):
        parse_program({"primitives": ["notanobject"]})
