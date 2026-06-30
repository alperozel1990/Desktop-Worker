"""inspect_3d — cheap, training-free 3D perception for the AI (Tier 3).

3D-app viewports are GPU-drawn and invisible to UI-Automation, and a single
screenshot is a poor handle on 3D shape/orientation. Research (Agent3D-Zero,
Think3D, Set-of-Mark / Set-of-Line prompting) shows a vision model reasons far
better over a *small set of views* than one: top-down reads global layout,
rotational views read orientation, K≈3 is enough and keeps cost bounded.

This tool captures several views and assembles ONE labelled montage image (with an
optional coordinate grid overlay) so the agent spends a single vision look instead
of many. It does NOT decide the views — the caller passes app-specific, VIEW-ONLY
setup steps (the AI knows e.g. Blender's Numpad/MMB-orbit), keeping it generic and
non-destructive (no clicks/typing that could modify the model).

Each view-setup step is one of (all gated by the emergency stop):
  {"key": "KP_1"}            -> press_key            (e.g. a Numpad view op)
  {"hotkey": ["CTRL","KP_1"]}-> hotkey
  {"orbit": [dx, dy]}        -> middle-drag by (dx,dy)  (the verified Blender orbit)
  {"move": [x, y]}           -> move cursor (e.g. into the viewport first)
  {"wait_ms": 200}           -> pause
"""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any

from desktop_worker.tools.registry import ToolError

_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp")
_MAX_VIEWS = 6  # cost cap: each tile is part of one vision look; K≈3 is the sweet spot


def build_montage(tile_paths: list[str], labels: list[str], grid: int,
                  out_path: Path, cell_w: int = 480) -> str | None:
    """Assemble tiles into one labelled montage PNG (optional NxN grid overlay).

    Lazy-imports Pillow; returns the montage path, or None if Pillow is missing or
    no tile is a real image (e.g. Null-backend placeholders). Best-effort per tile.
    """
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None

    label_h = 22
    cells: list[Any] = []
    for path, label in zip(tile_paths, labels):
        p = Path(path)
        if not (p.exists() and p.suffix.lower() in _IMAGE_SUFFIXES):
            continue
        try:
            img = Image.open(p).convert("RGB")
        except Exception:
            continue
        w, h = img.size
        ih = max(1, int(h * cell_w / w))
        img = img.resize((cell_w, ih))
        cell = Image.new("RGB", (cell_w, ih + label_h), (250, 250, 250))
        cell.paste(img, (0, label_h))
        draw = ImageDraw.Draw(cell)
        draw.text((4, 5), str(label), fill=(20, 20, 20))
        if grid and grid > 1:
            for i in range(1, grid):
                gx = cell_w * i // grid
                draw.line([(gx, label_h), (gx, label_h + ih)], fill=(255, 70, 70), width=1)
                gy = label_h + ih * i // grid
                draw.line([(0, gy), (cell_w, gy)], fill=(255, 70, 70), width=1)
            for i in range(grid):
                draw.text((cell_w * i // grid + 2, label_h + 2), str(i), fill=(255, 70, 70))
                draw.text((2, label_h + ih * i // grid + 1), str(i), fill=(255, 70, 70))
        cells.append(cell)

    if not cells:
        return None

    cols = min(len(cells), 3)
    rows = math.ceil(len(cells) / cols)
    cw = cell_w
    ch = max(c.size[1] for c in cells)
    montage = Image.new("RGB", (cols * cw, rows * ch), (255, 255, 255))
    for idx, cell in enumerate(cells):
        r, c = divmod(idx, cols)
        montage.paste(cell, (c * cw, r * ch))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    montage.save(out_path)
    return str(out_path)


class Inspect3DTool:
    """Capture several views of a 3D viewport into one montage for spatial reasoning."""

    name = "inspect_3d"
    description = (
        "Capture multiple views of a 3D viewport (Blender/Unity/CAD) and assemble them "
        "into ONE labelled montage image so you can reason about 3D shape/orientation in a "
        "single vision look. Pass `views`: a list (<=6, K~3 ideal) of view-setups; each view "
        "is a list of VIEW-ONLY steps applied before a screenshot — {key:'KP_1'} (press), "
        "{hotkey:['CTRL','KP_1']}, {orbit:[dx,dy]} (middle-drag, the verified Blender orbit), "
        "{move:[x,y]} (cursor into the viewport first), {wait_ms:200}. Optional `labels` "
        "(per view), `grid` (NxN coordinate overlay), `settle_ms`. Returns the montage path "
        "+ tile paths; then READ the montage to perceive the 3D structure."
    )
    args_help = ("views (list of step-lists; steps: {key}|{hotkey}|{orbit:[dx,dy]}|{move:[x,y]}|"
                 "{wait_ms}); optional labels (list[str]), grid (int NxN), settle_ms (int)")
    risk = "low"  # view-only navigation + screenshots; non-destructive

    def __init__(self, *, input_backend: Any, screenshot_fn: Any, estop: Any = None,
                 work_dir: Any = None) -> None:
        self._input = input_backend
        self._screenshot = screenshot_fn
        self._estop = estop
        self._work_dir = Path(work_dir) if work_dir else Path(".")

    def _check_estop(self) -> None:
        if self._estop is not None:
            from desktop_worker.safety.emergency_stop import EmergencyStopError
            try:
                self._estop.check()
            except EmergencyStopError as exc:
                raise ToolError(f"emergency stop: {exc}")

    def _apply(self, step: Any) -> None:
        if not isinstance(step, dict):
            raise ToolError(f"view step must be an object, got {type(step).__name__}")
        self._check_estop()
        ib = self._input
        if "key" in step:
            ib.press_key(str(step["key"]))
        elif "hotkey" in step:
            keys = step["hotkey"]
            if not isinstance(keys, (list, tuple)) or not keys:
                raise ToolError("hotkey step needs a non-empty list of keys")
            ib.hotkey([str(k) for k in keys])
        elif "orbit" in step:
            dx, dy = self._point(step["orbit"], "orbit")
            ib.mouse_down("middle"); ib.move_relative(dx, dy); ib.mouse_up("middle")
        elif "move" in step:
            x, y = self._point(step["move"], "move")
            ib.move(x, y)
        elif "wait_ms" in step:
            time.sleep(max(0, int(step["wait_ms"])) / 1000.0)
        else:
            raise ToolError(f"unknown view step {sorted(step)!r}; "
                            "allowed: key, hotkey, orbit, move, wait_ms")

    @staticmethod
    def _point(value: Any, field: str) -> tuple[int, int]:
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ToolError(f"{field} must be [x, y]")
        try:
            return int(value[0]), int(value[1])
        except (TypeError, ValueError):
            raise ToolError(f"{field} must be two integers")

    def run(self, args: dict[str, Any]) -> dict[str, Any]:
        views = args.get("views")
        if not isinstance(views, (list, tuple)) or not views:
            raise ToolError("inspect_3d needs a non-empty `views` list")
        if len(views) > _MAX_VIEWS:
            raise ToolError(f"too many views ({len(views)} > {_MAX_VIEWS}); keep K small (~3)")
        labels = args.get("labels")
        if labels is not None and (not isinstance(labels, (list, tuple))
                                   or len(labels) != len(views)):
            raise ToolError("labels, if given, must be a list the same length as views")
        labels = [str(l) for l in labels] if labels else [f"view {i+1}" for i in range(len(views))]
        grid = int(args.get("grid", 0) or 0)
        settle_ms = int(args.get("settle_ms", 250) or 0)

        self._work_dir.mkdir(parents=True, exist_ok=True)
        tiles: list[str] = []
        for i, steps in enumerate(views):
            if not isinstance(steps, (list, tuple)):
                raise ToolError(f"view {i} must be a list of steps")
            for step in steps:
                self._apply(step)
            if settle_ms:
                time.sleep(settle_ms / 1000.0)
            self._check_estop()
            dest = self._work_dir / f"view_{i+1}.png"
            shot = self._screenshot(dest)
            if shot:
                tiles.append(str(shot))

        if not tiles:
            return {"success": False, "error": "no screenshots were captured",
                    "views": len(views)}

        montage = build_montage(tiles, labels, grid, self._work_dir / "inspect_montage.png")
        return {"success": True, "montage": montage, "tiles": tiles,
                "labels": labels, "views": len(views),
                "note": None if montage else
                "montage skipped (Pillow missing or captures are not real images); "
                "read the individual tile paths instead",
                "error": None}
