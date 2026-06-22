"""Drawing DSL — a small, validated vector language on a 0..100 grid.

The AI plans a whole figure as a list of geometric *primitives* expressed on a
normalized grid (x and y both 0..100, origin top-left). Reasoning on a clean
grid — rather than guessing absolute screen pixels — is what makes the drawing
*controlled* (this is the SketchAgent idea). The grid is resolution-independent:
the same program renders correctly whatever size Paint's canvas is.

``parse_program`` is pure and raises :class:`ToolError` on any malformed input,
so a bad program can never reach the mouse. Out-of-range coordinates are
*clamped* into 0..100 (a slightly-off whisker shouldn't fail the whole figure);
non-finite or non-numeric values are rejected.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from desktop_worker.tools.registry import ToolError

MAX_PRIMITIVES = 200
_KINDS = ("line", "polyline", "circle", "ellipse", "arc", "bezier", "dot")


@dataclass(frozen=True)
class Primitive:
    """One normalized primitive: ``kind`` plus already-validated ``params``."""

    kind: str
    params: Dict[str, Any]


@dataclass(frozen=True)
class Program:
    title: str
    primitives: Tuple[Primitive, ...]


def _num(v: Any, where: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ToolError(f"{where}: expected a number, got {v!r}")
    f = float(v)
    if not math.isfinite(f):
        raise ToolError(f"{where}: number must be finite, got {v!r}")
    return f


def _clamp01(v: float) -> float:
    return min(100.0, max(0.0, v))


def _point(v: Any, where: str) -> Tuple[float, float]:
    if not isinstance(v, (list, tuple)) or len(v) != 2:
        raise ToolError(f"{where}: expected [x, y], got {v!r}")
    return (_clamp01(_num(v[0], where + "[x]")), _clamp01(_num(v[1], where + "[y]")))


def _points(v: Any, where: str, minimum: int) -> List[Tuple[float, float]]:
    if not isinstance(v, (list, tuple)) or len(v) < minimum:
        raise ToolError(f"{where}: expected >= {minimum} points, got {v!r}")
    return [_point(p, f"{where}[{i}]") for i, p in enumerate(v)]


def _parse_primitive(raw: Any, idx: int) -> Primitive:
    where = f"primitives[{idx}]"
    if not isinstance(raw, dict):
        raise ToolError(f"{where}: each primitive must be an object, got {raw!r}")
    kind = raw.get("kind")
    if kind not in _KINDS:
        raise ToolError(f"{where}: kind must be one of {_KINDS}, got {kind!r}")

    if kind == "line":
        p = {"from": _point(raw.get("from"), f"{where}.from"),
             "to": _point(raw.get("to"), f"{where}.to")}
    elif kind == "polyline":
        p = {"points": _points(raw.get("points"), f"{where}.points", 2),
             "closed": bool(raw.get("closed", False))}
    elif kind == "circle":
        p = {"center": _point(raw.get("center"), f"{where}.center"),
             "r": _clamp01(_num(raw.get("r"), f"{where}.r"))}
    elif kind == "ellipse":
        p = {"center": _point(raw.get("center"), f"{where}.center"),
             "rx": _clamp01(_num(raw.get("rx"), f"{where}.rx")),
             "ry": _clamp01(_num(raw.get("ry"), f"{where}.ry")),
             "rotation": _num(raw.get("rotation", 0), f"{where}.rotation")}
    elif kind == "arc":
        p = {"center": _point(raw.get("center"), f"{where}.center"),
             "r": _clamp01(_num(raw.get("r"), f"{where}.r")),
             "start": _num(raw.get("start"), f"{where}.start"),
             "end": _num(raw.get("end"), f"{where}.end")}
        if p["start"] == p["end"]:
            raise ToolError(f"{where}: arc start and end must differ (got {p['start']})")
    elif kind == "bezier":
        pts = _points(raw.get("points"), f"{where}.points", 3)
        if len(pts) not in (3, 4):
            raise ToolError(f"{where}.points: bezier needs 3 (quadratic) or 4 (cubic) "
                            f"points, got {len(pts)}")
        p = {"points": pts}
    else:  # dot
        p = {"at": _point(raw.get("at"), f"{where}.at")}

    return Primitive(kind=kind, params=p)


def parse_program(args: Dict[str, Any]) -> Program:
    """Validate AI-supplied draw args into a normalized Program (pure)."""
    if not isinstance(args, dict):
        raise ToolError("sketch args must be an object")
    raw_prims = args.get("primitives")
    if not isinstance(raw_prims, (list, tuple)) or not raw_prims:
        raise ToolError("sketch needs a non-empty 'primitives' list")
    if len(raw_prims) > MAX_PRIMITIVES:
        raise ToolError(f"too many primitives ({len(raw_prims)} > {MAX_PRIMITIVES})")
    prims = tuple(_parse_primitive(r, i) for i, r in enumerate(raw_prims))
    title = str(args.get("title", "drawing"))[:80]
    return Program(title=title, primitives=prims)
