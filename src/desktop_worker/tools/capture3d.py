"""capture_burst + orbit — Tier 2 3D capabilities.

The user's ask: take fast, time-stamped snapshots WHILE rotating a 3D view.

- `capture_burst` holds a middle-drag across the whole sweep (one continuous orbit) and grabs a
  frame at each eased sub-step, recording a relative ms timestamp per frame, then assembles a
  contact-sheet montage. Optionally (`fast:true` + the `[capture]` extra) it grabs via DXcam (DXGI
  Desktop Duplication, far faster than mss for tight in-motion frames); otherwise it uses the same
  screenshot path as everything else.
- `orbit` is a one-call eased middle-drag — the convenience version of inspect_3d's internal orbit
  (eased + time-spaced so it registers on Blender's GHOST input, where an instant jump is dropped).

Both are VIEW-ONLY (no clicks/typing) and emergency-stop-gated, like Sketch/DragDrop/inspect_3d.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from desktop_worker.tools.inspect3d import build_montage
from desktop_worker.tools.registry import ToolError


def _point(value: Any, field: str) -> tuple[int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ToolError(f"{field} must be [x, y]")
    try:
        return int(value[0]), int(value[1])
    except (TypeError, ValueError):
        raise ToolError(f"{field} must be two integers")


def eased_orbit(ib: Any, dx: int, dy: int, *, steps: int = 10, settle: float = 0.08,
                step_delay: float = 0.02, check: Any = None, on_step: Any = None) -> None:
    """Hold MMB and move in eased sub-steps so the app registers a real orbit drag.

    A single instantaneous jump while MMB is held is dropped by apps that integrate
    mouse-move deltas (Blender's GHOST layer). `on_step(i)` fires after each sub-step
    (used by capture_burst to grab a frame mid-orbit).
    """
    ib.mouse_down("middle")
    try:
        if check:
            check()
        time.sleep(settle)
        acc_x = acc_y = 0
        for i in range(1, steps + 1):
            tx, ty = round(dx * i / steps), round(dy * i / steps)
            mx, my = tx - acc_x, ty - acc_y
            acc_x, acc_y = tx, ty
            if mx or my:
                ib.move_relative(mx, my)
            time.sleep(step_delay)
            if check:
                check()
            if on_step:
                on_step(i)
        time.sleep(settle)
    finally:
        ib.mouse_up("middle")


def _estop_checker(estop: Any):
    def check() -> None:
        if estop is not None:
            from desktop_worker.safety.emergency_stop import EmergencyStopError
            try:
                estop.check()
            except EmergencyStopError as exc:
                raise ToolError(f"emergency stop: {exc}")
    return check


def make_dxcam_grabber():
    """Return a fast full-screen grab(dest)->path via DXcam, or None if unavailable.

    Lazy + fully guarded: missing dxcam/Pillow, or a failed camera, yields None so the
    caller falls back to the normal screenshot path.
    """
    try:
        import dxcam  # type: ignore
        from PIL import Image
    except Exception:
        return None
    try:
        cam = dxcam.create()
    except Exception:
        cam = None
    if cam is None:
        return None

    def grab(dest: Path) -> str | None:
        try:
            frame = cam.grab()  # BGR/RGB numpy ndarray, or None if no new frame
            if frame is None:
                return None
            Image.fromarray(frame).save(dest)
            return str(dest)
        except Exception:
            return None

    return grab


class OrbitTool:
    """Orbit a 3D viewport by an eased middle-drag (one call)."""

    name = "orbit"
    description = (
        "Orbit a 3D viewport by an eased middle-mouse drag — it registers on Blender's GHOST input "
        "(an instant jump is dropped). Args: delta:[dx,dy] (~250-330 px = a big swing; +dx yaws, -dy "
        "tilts toward top-down), move:[cx,cy] (cursor INTO the viewport first — the app orbits around "
        "it), optional steps. Non-destructive view change; follow with `screenshot` to see it."
    )
    args_help = "delta:[dx,dy]; optional move:[cx,cy], steps (int)"
    risk = "low"

    def __init__(self, *, input_backend: Any, estop: Any = None) -> None:
        self._input = input_backend
        self._check = _estop_checker(estop)

    def run(self, args: dict[str, Any]) -> dict[str, Any]:
        dx, dy = _point(args.get("delta"), "delta")
        self._check()
        mv = args.get("move")
        if mv is not None:
            mx, my = _point(mv, "move")
            self._input.move(mx, my)
        steps = max(1, int(args.get("steps", 10) or 10))
        eased_orbit(self._input, dx, dy, steps=steps, check=self._check)
        return {"success": True, "delta": [dx, dy], "error": None}


class CaptureBurstTool:
    """Capture N timestamped frames while orbiting, into one contact-sheet montage."""

    name = "capture_burst"
    description = (
        "Capture N timestamped frames WHILE orbiting a 3D view (snapshots-while-rotating) and "
        "assemble them into one contact-sheet montage. Holds a single middle-drag across the whole "
        "sweep (continuous orbit) and grabs a frame at each eased step. Args: orbit:[dx,dy] total "
        "motion, frames:N (2..12), move:[cx,cy] (cursor into the viewport first), optional crop:"
        "[l,t,r,b], grid (NxN), cols, fast:true (use DXcam if the [capture] extra is installed). "
        "Returns the frames, per-frame ms timestamps, and the montage path — READ the montage."
    )
    args_help = ("orbit:[dx,dy]; frames (int 2..12); optional move:[cx,cy], crop:[l,t,r,b], "
                 "grid (int), cols (int), fast (bool)")
    risk = "low"
    MAX_FRAMES = 12

    def __init__(self, *, input_backend: Any, screenshot_fn: Any, estop: Any = None,
                 work_dir: Any = None) -> None:
        self._input = input_backend
        self._screenshot = screenshot_fn
        self._check = _estop_checker(estop)
        self._work_dir = Path(work_dir) if work_dir else Path(".")

    def run(self, args: dict[str, Any]) -> dict[str, Any]:
        dx, dy = _point(args.get("orbit"), "orbit")
        frames = int(args.get("frames", 6) or 6)
        if frames < 2 or frames > self.MAX_FRAMES:
            raise ToolError(f"frames must be 2..{self.MAX_FRAMES}")
        crop = args.get("crop")
        if crop is not None and (not isinstance(crop, (list, tuple)) or len(crop) != 4):
            raise ToolError("crop must be [left, top, right, bottom]")
        grid = int(args.get("grid", 0) or 0)
        cols = int(args["cols"]) if args.get("cols") else None

        grabber = make_dxcam_grabber() if args.get("fast") else None
        capture = grabber or self._screenshot

        self._work_dir.mkdir(parents=True, exist_ok=True)
        self._check()
        mv = args.get("move")
        if mv is not None:
            mx, my = _point(mv, "move")
            self._input.move(mx, my)

        tiles: list[str] = []
        stamps: list[int] = []
        t0 = time.perf_counter()

        def grab(i: int) -> None:
            dest = self._work_dir / f"burst_{i:02d}.png"
            shot = capture(dest)
            if shot:
                tiles.append(str(shot))
                stamps.append(round((time.perf_counter() - t0) * 1000))

        grab(0)  # frame before motion
        eased_orbit(self._input, dx, dy, steps=frames - 1, settle=0.06,
                    check=self._check, on_step=grab)

        if not tiles:
            return {"success": False, "error": "no frames were captured", "frames": []}

        labels = [f"{s} ms" for s in stamps]
        montage = build_montage(tiles, labels, grid,
                                self._work_dir / "burst_montage.png", crop=crop, cols=cols)
        notes: list[str] = []
        if args.get("fast") and grabber is None:
            notes.append("fast requested but DXcam (the [capture] extra) is not installed — "
                         "used the default capture instead")
        if not montage:
            notes.append("montage skipped (Pillow missing or non-image captures); read the frames")
        return {"success": True, "montage": montage, "frames": tiles,
                "timestamps_ms": stamps, "count": len(tiles),
                "fast": bool(grabber),
                "note": " | ".join(notes) or None,
                "error": None}
