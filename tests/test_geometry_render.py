"""Tests for the pure vector renderer (tessellation + canvas mapping)."""

import math

from desktop_worker.geometry.canvas import CanvasRect
from desktop_worker.geometry.dsl import parse_program
from desktop_worker.geometry.render import (compile_program, map_point, samples_for,
                                            tess_arc, tess_bezier, tess_circle,
                                            tess_dot, tess_ellipse, tess_line,
                                            tess_polyline)

CANVAS = CanvasRect(100, 100, 900, 700, source="null")  # 800x600


# --- adaptive sampling ---------------------------------------------------

def test_samples_for_monotonic_and_clamped():
    assert samples_for(0) == 12          # min clamp
    assert samples_for(10_000) == 240    # max clamp
    assert samples_for(600) >= samples_for(120)   # more pixels => more samples


# --- tessellation: circle is a TRUE circle (not a polygon) ---------------

def test_circle_points_are_on_the_radius():
    pts = tess_circle((50, 40), 22, 64)
    for x, y in pts:
        assert abs(math.hypot(x - 50, y - 40) - 22) < 1e-6
    assert pts[0] == pts[-1]             # closed loop


def test_circle_dense_enough_to_look_round():
    # A 22-unit radius on an 800px-wide canvas => big circle => many samples.
    strokes = compile_program(parse_program(
        {"primitives": [{"kind": "circle", "center": [50, 40], "r": 22}]}), CANVAS)
    assert len(strokes[0]) >= 40         # not a hexagon


# --- tessellation: other primitives --------------------------------------

def test_line_and_polyline():
    assert tess_line((10, 10), (20, 30)) == [(10, 10), (20, 30)]
    assert tess_polyline([(0, 0), (1, 1)], closed=True) == [(0, 0), (1, 1), (0, 0)]


def test_bezier_endpoints_match_controls():
    quad = tess_bezier([(0, 0), (50, 100), (100, 0)], 20)
    assert quad[0] == (0, 0) and quad[-1] == (100, 0)
    cubic = tess_bezier([(0, 0), (0, 100), (100, 100), (100, 0)], 20)
    assert cubic[0] == (0, 0) and cubic[-1] == (100, 0)


def test_arc_spans_only_requested_angles():
    pts = tess_arc((50, 50), 10, 0, 90, 16)
    assert abs(pts[0][0] - 60) < 1e-6 and abs(pts[0][1] - 50) < 1e-6      # 0deg -> +x
    assert abs(pts[-1][0] - 50) < 1e-6 and abs(pts[-1][1] - 60) < 1e-6    # 90deg -> +y


def test_ellipse_rotation_zero_major_axis():
    pts = tess_ellipse((50, 50), 20, 10, 0.0, 32)
    assert abs(pts[0][0] - 70) < 1e-6 and abs(pts[0][1] - 50) < 1e-6      # rx along x


def test_dot_is_two_identical_points():
    assert tess_dot((30, 40)) == [(30, 40), (30, 40)]


# --- normalized -> canvas pixel mapping ----------------------------------

def test_map_point_corners_and_center():
    assert map_point((0, 0), CANVAS) == (100, 100)        # top-left
    assert map_point((100, 100), CANVAS) == (900, 700)    # bottom-right
    assert map_point((50, 50), CANVAS) == (500, 400)      # center


def test_map_point_clamps_out_of_range():
    assert map_point((-50, 200), CANVAS) == (100, 700)    # clamped to canvas bounds


# --- compile_program: one stroke per primitive (no fusion / no slash) ----

def test_compile_one_stroke_per_primitive():
    program = parse_program({"title": "cat", "primitives": [
        {"kind": "circle", "center": [50, 40], "r": 22},
        {"kind": "polyline", "points": [[33, 22], [28, 8], [42, 26]], "closed": True},
        {"kind": "dot", "at": [50, 46]},
        {"kind": "line", "from": [30, 50], "to": [10, 47]},
        {"kind": "bezier", "points": [[72, 55], [92, 60], [80, 80]]},
    ]})
    strokes = compile_program(program, CANVAS)
    assert len(strokes) == 5                          # exactly one stroke per primitive
    for s in strokes:
        assert len(s) >= 2                            # every stroke is drawable
        for x, y in s:                                # every point inside the canvas
            assert 100 <= x <= 900 and 100 <= y <= 700
