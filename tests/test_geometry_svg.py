"""Tests for the SVG-subset -> Program parser."""

import math

import pytest

from desktop_worker.geometry.svg import parse_svg
from desktop_worker.tools.registry import ToolError


def test_parses_basic_shapes_with_viewbox():
    svg = ('<svg viewBox="0 0 100 100">'
           '<circle cx="50" cy="50" r="25"/>'
           '<line x1="0" y1="0" x2="100" y2="100"/>'
           '<rect x="10" y="10" width="20" height="20"/>'
           '</svg>')
    prog = parse_svg(svg)
    kinds = [p.kind for p in prog.primitives]
    assert kinds == ["circle", "line", "polyline"]      # rect -> closed polyline
    # viewBox is square 100x100 -> identity-ish mapping (centered, full fit).
    c = prog.primitives[0]
    assert abs(c.params["center"][0] - 50) < 1e-6 and abs(c.params["r"] - 25) < 1e-6


def test_path_curves_become_one_continuous_polyline():
    # One subpath with a cubic -> a single dense polyline (continuous pen stroke).
    svg = '<svg viewBox="0 0 100 100"><path d="M 10 10 C 30 90 70 90 90 10"/></svg>'
    prog = parse_svg(svg)
    assert len(prog.primitives) == 1
    poly = prog.primitives[0]
    assert poly.kind == "polyline"
    assert len(poly.params["points"]) > 10              # curve sampled densely


def test_multiple_subpaths_become_multiple_strokes():
    svg = '<svg viewBox="0 0 100 100"><path d="M0 0 L 10 10 Z M 50 50 L 60 60"/></svg>'
    prog = parse_svg(svg)
    assert len(prog.primitives) == 2                    # two subpaths = two strokes


def test_relative_commands_and_close():
    svg = '<svg viewBox="0 0 100 100"><path d="M 10 10 l 20 0 l 0 20 z"/></svg>'
    prog = parse_svg(svg)
    poly = prog.primitives[0]
    assert poly.kind == "polyline"
    # closed: last point returns to start (within the normalized space)
    assert poly.params["points"][0] == poly.params["points"][-1]


def test_autofit_without_viewbox_preserves_aspect():
    # No viewBox: a circle far from origin in a big coordinate space must be fit
    # into 0..100 and stay a circle (rx==ry preserved via uniform scale).
    svg = '<svg><circle cx="1000" cy="1000" r="500"/></svg>'
    prog = parse_svg(svg)
    c = prog.primitives[0].params
    assert 0 <= c["center"][0] <= 100 and 0 <= c["center"][1] <= 100
    assert c["r"] > 0


def test_rejects_non_svg_and_empty():
    with pytest.raises(ToolError):
        parse_svg("not svg")
    with pytest.raises(ToolError):
        parse_svg("<svg></svg>")               # no drawable elements


def test_truncated_path_fails_safe_not_crash():
    # A malformed/truncated path must be SKIPPED (ToolError if nothing else drawable),
    # never an uncaught IndexError. A valid sibling shape still parses.
    with pytest.raises(ToolError):
        parse_svg('<svg viewBox="0 0 100 100"><path d="M 10"/></svg>')   # missing Y
    with pytest.raises(ToolError):
        parse_svg('<svg viewBox="0 0 100 100"><path d="C 1 2 3"/></svg>')  # too few
    prog = parse_svg('<svg viewBox="0 0 100 100">'
                     '<path d="M 10"/><circle cx="50" cy="50" r="20"/></svg>')
    assert [p.kind for p in prog.primitives] == ["circle"]   # bad path skipped, circle kept


def test_cat_svg_smoke():
    svg = ('<svg viewBox="0 0 100 100">'
           '<circle cx="50" cy="42" r="22"/>'
           '<polygon points="33,24 28,8 44,28"/>'
           '<circle cx="42" cy="40" r="3"/>'
           '<circle cx="58" cy="40" r="3"/>'
           '<path d="M 40 50 Q 50 58 60 50"/>'      # smile
           '<ellipse cx="50" cy="78" rx="16" ry="13"/>'
           '</svg>')
    prog = parse_svg(svg)
    assert len(prog.primitives) == 6
    assert all(0 <= pt[0] <= 100 and 0 <= pt[1] <= 100
               for p in prog.primitives if p.kind == "polyline"
               for pt in p.params["points"])
