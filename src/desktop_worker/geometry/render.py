"""Deterministic vector tessellation — the "smart" half of controlled drawing.

Pure and dependency-free (no ctypes, no platform imports): given a validated
:class:`~desktop_worker.geometry.dsl.Program` (primitives on a 0..100 grid) and a
:class:`~desktop_worker.geometry.canvas.CanvasRect` (where Paint's real canvas is),
``compile_program`` produces one **stroke per primitive** in absolute canvas
pixels — a stroke being a dense list of ``(x, y)`` points the input backend can
draw as a continuous line.

Two design choices fix the old failures:

* **Adaptive sampling** (``samples_for``) packs ~1 point per ~6 rendered pixels,
  so circles/curves are smooth at any canvas size — no more polygon circles.
* **One primitive == one stroke.** The renderer never concatenates two
  primitives into a single point list, so there is never a connecting segment
  between, say, the head circle and an ear — the old "stray diagonal slash" is
  impossible by construction.
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

from desktop_worker.geometry.canvas import CanvasRect
from desktop_worker.geometry.dsl import Primitive, Program

Point = Tuple[float, float]
Stroke = List[Tuple[int, int]]

# Adaptive sampling bounds: aim for ~1 sample per _PX_PER_SAMPLE rendered pixels,
# clamped so tiny shapes still curve and huge shapes stay cheap.
_PX_PER_SAMPLE = 6.0
_MIN_SAMPLES = 12
_MAX_SAMPLES = 240


def samples_for(length_px: float) -> int:
    """Number of samples for a curve of the given rendered length (pixels)."""
    n = int(length_px / _PX_PER_SAMPLE)
    return max(_MIN_SAMPLES, min(_MAX_SAMPLES, n))


# --- normalized-space tessellation (0..100 grid) -------------------------
# Each returns a list of (x, y) points in 0..100 space. `n` is the sample count
# for curved primitives (chosen adaptively by compile_program from pixel size).

def tess_line(a: Point, b: Point) -> List[Point]:
    return [(a[0], a[1]), (b[0], b[1])]


def tess_polyline(points: Sequence[Point], closed: bool = False) -> List[Point]:
    pts = [(p[0], p[1]) for p in points]
    if closed and pts:
        pts = pts + [pts[0]]
    return pts


def tess_circle(center: Point, r: float, n: int) -> List[Point]:
    cx, cy = center
    n = max(3, n)
    out = [(cx + r * math.cos(2 * math.pi * i / n),
            cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    out.append(out[0])  # close the loop
    return out


def tess_ellipse(center: Point, rx: float, ry: float, rotation: float, n: int) -> List[Point]:
    cx, cy = center
    n = max(3, n)
    ca, sa = math.cos(math.radians(rotation)), math.sin(math.radians(rotation))
    out: List[Point] = []
    for i in range(n):
        t = 2 * math.pi * i / n
        ex, ey = rx * math.cos(t), ry * math.sin(t)
        out.append((cx + ex * ca - ey * sa, cy + ex * sa + ey * ca))
    out.append(out[0])
    return out


def tess_arc(center: Point, r: float, start: float, end: float, n: int) -> List[Point]:
    cx, cy = center
    a0, a1 = math.radians(start), math.radians(end)
    n = max(2, n)
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / n),
             cy + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]


def tess_bezier(points: Sequence[Point], n: int) -> List[Point]:
    """Sample a quadratic (3 control points) or cubic (4) Bezier via de Casteljau."""
    ctrl = [(p[0], p[1]) for p in points]
    n = max(2, n)
    return [_de_casteljau(ctrl, i / n) for i in range(n + 1)]


def _de_casteljau(ctrl: List[Point], t: float) -> Point:
    pts = list(ctrl)
    while len(pts) > 1:
        pts = [((1 - t) * a[0] + t * b[0], (1 - t) * a[1] + t * b[1])
               for a, b in zip(pts, pts[1:])]
    return pts[0]


def tess_dot(at: Point) -> List[Point]:
    # Two identical points => the backend presses, "moves" nowhere, releases: a dot.
    return [(at[0], at[1]), (at[0], at[1])]


# --- normalized -> canvas pixels -----------------------------------------

def map_point(p: Point, canvas: CanvasRect) -> Tuple[int, int]:
    """Affine-map a 0..100 grid point into absolute canvas pixels (clamped)."""
    x = canvas.left + (p[0] / 100.0) * canvas.width
    y = canvas.top + (p[1] / 100.0) * canvas.height
    x = min(canvas.right, max(canvas.left, x))
    y = min(canvas.bottom, max(canvas.top, y))
    return int(round(x)), int(round(y))


def _avg_scale(canvas: CanvasRect) -> float:
    """Average pixels per normalized unit (canvas is 100 units wide/tall)."""
    return (canvas.width + canvas.height) / 200.0


def _tessellate(prim: Primitive, canvas: CanvasRect) -> List[Point]:
    """Tessellate one primitive in normalized space, sample count from pixel size."""
    k, p, scale = prim.kind, prim.params, _avg_scale(canvas)
    if k == "line":
        return tess_line(p["from"], p["to"])
    if k == "polyline":
        return tess_polyline(p["points"], p.get("closed", False))
    if k == "dot":
        return tess_dot(p["at"])
    if k == "circle":
        return tess_circle(p["center"], p["r"], samples_for(2 * math.pi * p["r"] * scale))
    if k == "ellipse":
        avg_r = (p["rx"] + p["ry"]) / 2.0
        return tess_ellipse(p["center"], p["rx"], p["ry"], p.get("rotation", 0.0),
                            samples_for(2 * math.pi * avg_r * scale))
    if k == "arc":
        span = abs(p["end"] - p["start"]) / 360.0
        return tess_arc(p["center"], p["r"], p["start"], p["end"],
                        samples_for(2 * math.pi * p["r"] * span * scale))
    if k == "bezier":
        ctrl = p["points"]
        poly = sum(math.dist(a, b) for a, b in zip(ctrl, ctrl[1:]))
        return tess_bezier(ctrl, samples_for(poly * scale))
    raise ValueError(f"unknown primitive kind: {k!r}")  # pragma: no cover (dsl guards)


def compile_program(program: Program, canvas: CanvasRect) -> List[Stroke]:
    """Compile a program into one pixel-space stroke per primitive (pure)."""
    strokes: List[Stroke] = []
    for prim in program.primitives:
        norm = _tessellate(prim, canvas)
        strokes.append([map_point(pt, canvas) for pt in norm])
    return strokes
