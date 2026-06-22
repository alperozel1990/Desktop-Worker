"""SVG (subset) -> drawing Program. LLMs generate SVG far better than a bespoke
DSL (trained on millions of SVGs), so accepting SVG raises drawing quality while
reusing the v1 renderer + canvas detection unchanged.

Supported: ``<path>`` (M/L/H/V/C/Q/S/T/Z + relative; A approximated as a line),
``<circle>``, ``<ellipse>``, ``<line>``, ``<polyline>``, ``<polygon>``, ``<rect>``.
All geometry is collected in SVG space, then fit into the 0..100 grid PRESERVING
aspect ratio (matching SVG's default ``xMidYMid meet``) — using the ``viewBox`` if
present, else the geometry's bounding box (robust to any coordinate scale the model
emits). Each path subpath becomes ONE continuous polyline (curves sampled), so a
pen stroke stays continuous. The result is validated through ``dsl.parse_program``.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Tuple

from desktop_worker.geometry.dsl import Program, parse_program
from desktop_worker.tools.registry import ToolError

Point = Tuple[float, float]
_BEZIER_SAMPLES = 24

_NUM = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
_CMD = re.compile(r"[MmLlHhVvCcQqSsTtAaZz]")
_TAG = re.compile(r"<(path|circle|ellipse|line|polyline|polygon|rect)\b([^>]*)/?>",
                  re.IGNORECASE)
_ATTR = re.compile(r'([\w:-]+)\s*=\s*"([^"]*)"')


def _floats(s: str) -> List[float]:
    return [float(m.group()) for m in _NUM.finditer(s)]


def _bezier(p0: Point, p1: Point, p2: Point, p3: Point, n: int) -> List[Point]:
    out = []
    for i in range(1, n + 1):
        t = i / n
        mt = 1 - t
        x = mt**3*p0[0] + 3*mt*mt*t*p1[0] + 3*mt*t*t*p2[0] + t**3*p3[0]
        y = mt**3*p0[1] + 3*mt*mt*t*p1[1] + 3*mt*t*t*p2[1] + t**3*p3[1]
        out.append((x, y))
    return out


def _quad(p0: Point, p1: Point, p2: Point, n: int) -> List[Point]:
    out = []
    for i in range(1, n + 1):
        t = i / n
        mt = 1 - t
        out.append((mt*mt*p0[0] + 2*mt*t*p1[0] + t*t*p2[0],
                    mt*mt*p0[1] + 2*mt*t*p1[1] + t*t*p2[1]))
    return out


def _parse_path(d: str) -> List[List[Point]]:
    """Path data -> list of subpaths (each a list of points in SVG space)."""
    tokens = re.findall(r"[MmLlHhVvCcQqSsTtAaZz]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?", d)
    subpaths: List[List[Point]] = []
    cur: List[Point] = []
    x = y = sx = sy = 0.0
    prev_cubic_ctrl = prev_quad_ctrl = None
    i = 0
    cmd = None
    nums: List[float] = []

    def nextf() -> float:
        nonlocal i
        if i >= len(tokens):                 # truncated path (e.g. "M 10", "C 1 2 3")
            raise ValueError("truncated SVG path data")
        v = float(tokens[i]); i += 1
        return v

    while i < len(tokens):
        t = tokens[i]
        if _CMD.fullmatch(t):
            cmd = t
            i += 1
        if cmd is None:
            i += 1
            continue
        rel = cmd.islower()
        c = cmd.upper()
        if c == "Z":
            if cur:
                cur.append((sx, sy)); subpaths.append(cur); cur = []
            prev_cubic_ctrl = prev_quad_ctrl = None
            continue
        if c == "M":
            nx, ny = nextf(), nextf()
            x, y = (x+nx, y+ny) if rel else (nx, ny)
            if cur:
                subpaths.append(cur)
            cur = [(x, y)]; sx, sy = x, y
            cmd = "l" if rel else "L"   # subsequent pairs are implicit lineto
            prev_cubic_ctrl = prev_quad_ctrl = None
            continue
        if c == "L":
            nx, ny = nextf(), nextf()
            x, y = (x+nx, y+ny) if rel else (nx, ny)
            cur.append((x, y)); prev_cubic_ctrl = prev_quad_ctrl = None
        elif c == "H":
            nx = nextf(); x = x+nx if rel else nx
            cur.append((x, y)); prev_cubic_ctrl = prev_quad_ctrl = None
        elif c == "V":
            ny = nextf(); y = y+ny if rel else ny
            cur.append((x, y)); prev_cubic_ctrl = prev_quad_ctrl = None
        elif c == "C":
            x1, y1, x2, y2, nx, ny = (nextf() for _ in range(6))
            if rel:
                x1, y1, x2, y2, nx, ny = x+x1, y+y1, x+x2, y+y2, x+nx, y+ny
            cur += _bezier((x, y), (x1, y1), (x2, y2), (nx, ny), _BEZIER_SAMPLES)
            prev_cubic_ctrl = (x2, y2); prev_quad_ctrl = None; x, y = nx, ny
        elif c == "S":
            x2, y2, nx, ny = (nextf() for _ in range(4))
            if rel:
                x2, y2, nx, ny = x+x2, y+y2, x+nx, y+ny
            x1, y1 = (2*x - prev_cubic_ctrl[0], 2*y - prev_cubic_ctrl[1]) if prev_cubic_ctrl else (x, y)
            cur += _bezier((x, y), (x1, y1), (x2, y2), (nx, ny), _BEZIER_SAMPLES)
            prev_cubic_ctrl = (x2, y2); prev_quad_ctrl = None; x, y = nx, ny
        elif c == "Q":
            x1, y1, nx, ny = (nextf() for _ in range(4))
            if rel:
                x1, y1, nx, ny = x+x1, y+y1, x+nx, y+ny
            cur += _quad((x, y), (x1, y1), (nx, ny), _BEZIER_SAMPLES)
            prev_quad_ctrl = (x1, y1); prev_cubic_ctrl = None; x, y = nx, ny
        elif c == "T":
            nx, ny = nextf(), nextf()
            if rel:
                nx, ny = x+nx, y+ny
            x1, y1 = (2*x - prev_quad_ctrl[0], 2*y - prev_quad_ctrl[1]) if prev_quad_ctrl else (x, y)
            cur += _quad((x, y), (x1, y1), (nx, ny), _BEZIER_SAMPLES)
            prev_quad_ctrl = (x1, y1); prev_cubic_ctrl = None; x, y = nx, ny
        elif c == "A":
            # Arc — approximate as a straight line to the endpoint (rare in sketches).
            for _ in range(5):
                nextf()
            nx, ny = nextf(), nextf()
            x, y = (x+nx, y+ny) if rel else (nx, ny)
            cur.append((x, y)); prev_cubic_ctrl = prev_quad_ctrl = None
        else:
            i += 1
    if cur:
        subpaths.append(cur)
    return [sp for sp in subpaths if len(sp) >= 2]


# Intermediate primitive in SVG space: dict with kind + svg-space geometry.
def _shapes_from_svg(svg: str) -> List[Dict[str, Any]]:
    shapes: List[Dict[str, Any]] = []
    for m in _TAG.finditer(svg):
        tag = m.group(1).lower()
        attrs = {k.lower(): v for k, v in _ATTR.findall(m.group(2))}
        try:
            if tag == "path" and attrs.get("d"):
                for sp in _parse_path(attrs["d"]):
                    shapes.append({"kind": "polyline", "points": sp})
            elif tag == "circle":
                shapes.append({"kind": "circle",
                               "center": (float(attrs["cx"]), float(attrs["cy"])),
                               "r": float(attrs["r"])})
            elif tag == "ellipse":
                shapes.append({"kind": "ellipse",
                               "center": (float(attrs["cx"]), float(attrs["cy"])),
                               "rx": float(attrs["rx"]), "ry": float(attrs["ry"])})
            elif tag == "line":
                shapes.append({"kind": "line",
                               "from": (float(attrs["x1"]), float(attrs["y1"])),
                               "to": (float(attrs["x2"]), float(attrs["y2"]))})
            elif tag in ("polyline", "polygon"):
                f = _floats(attrs.get("points", ""))
                pts = list(zip(f[0::2], f[1::2]))
                if len(pts) >= 2:
                    shapes.append({"kind": "polyline", "points": pts,
                                   "closed": tag == "polygon"})
            elif tag == "rect":
                rx, ry = float(attrs["x"]), float(attrs["y"])
                rw, rh = float(attrs["width"]), float(attrs["height"])
                shapes.append({"kind": "polyline", "closed": True,
                               "points": [(rx, ry), (rx+rw, ry), (rx+rw, ry+rh), (rx, ry+rh)]})
        except (KeyError, ValueError):
            continue   # skip a malformed element, keep the rest
    return shapes


def _extent_points(shapes: List[Dict[str, Any]]) -> List[Point]:
    pts: List[Point] = []
    for s in shapes:
        k = s["kind"]
        if k == "polyline":
            pts += list(s["points"])
        elif k == "line":
            pts += [s["from"], s["to"]]
        elif k == "circle":
            cx, cy = s["center"]; r = s["r"]
            pts += [(cx-r, cy-r), (cx+r, cy+r)]
        elif k == "ellipse":
            cx, cy = s["center"]; rx, ry = s["rx"], s["ry"]
            pts += [(cx-rx, cy-ry), (cx+rx, cy+ry)]
    return pts


def _viewbox(svg: str):
    m = re.search(r'viewBox\s*=\s*"([^"]+)"', svg)
    if m:
        f = _floats(m.group(1))
        if len(f) == 4 and f[2] > 0 and f[3] > 0:
            return f[0], f[1], f[2], f[3]
    return None


def parse_svg(svg: str, *, title: str = "drawing") -> Program:
    """Parse an SVG-subset string into a validated 0..100-grid Program."""
    if not isinstance(svg, str) or "<" not in svg:
        raise ToolError("svg must be an SVG string")
    shapes = _shapes_from_svg(svg)
    if not shapes:
        raise ToolError("no drawable SVG elements found (path/circle/ellipse/line/poly/rect)")

    vb = _viewbox(svg)
    if vb:
        bx, by, bw, bh = vb
    else:
        ext = _extent_points(shapes)
        xs = [p[0] for p in ext]; ys = [p[1] for p in ext]
        bx, by = min(xs), min(ys)
        bw, bh = max(1e-6, max(xs) - bx), max(1e-6, max(ys) - by)

    # Fit the source box into 0..100 preserving aspect (xMidYMid meet), centered.
    s = 100.0 / max(bw, bh)
    ox = (100.0 - bw * s) / 2.0
    oy = (100.0 - bh * s) / 2.0

    def tx(p: Point) -> List[float]:
        return [(p[0] - bx) * s + ox, (p[1] - by) * s + oy]

    prims: List[Dict[str, Any]] = []
    for sh in shapes:
        k = sh["kind"]
        if k == "polyline":
            prims.append({"kind": "polyline", "points": [tx(p) for p in sh["points"]],
                          "closed": bool(sh.get("closed", False))})
        elif k == "line":
            prims.append({"kind": "line", "from": tx(sh["from"]), "to": tx(sh["to"])})
        elif k == "circle":
            c = tx(sh["center"]); prims.append({"kind": "circle", "center": c, "r": sh["r"] * s})
        elif k == "ellipse":
            c = tx(sh["center"])
            prims.append({"kind": "ellipse", "center": c, "rx": sh["rx"] * s, "ry": sh["ry"] * s})

    m = re.search(r"<title>([^<]*)</title>", svg)
    return parse_program({"title": (m.group(1) if m else title), "primitives": prims})
