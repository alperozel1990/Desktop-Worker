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

import hashlib
import math
import time
from pathlib import Path
from typing import Any

from desktop_worker.tools.registry import ToolError

_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp")
_MAX_VIEWS = 6  # cost cap: each tile is part of one vision look; K≈3 is the sweet spot


def build_montage(tile_paths: list[str], labels: list[str], grid: int,
                  out_path: Path, cell_w: int = 480, crop: Any = None,
                  cols: int | None = None) -> str | None:
    """Assemble tiles into one labelled montage PNG (optional NxN grid overlay).

    ``crop`` (optional [left, top, right, bottom]) crops every tile to that box
    first — pass the viewport bounds so the 3D subject fills the tile instead of the
    full window. Lazy-imports Pillow; returns the montage path, or None if Pillow is
    missing or no tile is a real image (e.g. Null-backend placeholders).
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
        if crop:
            l, t, r, b = crop
            img = img.crop((max(0, l), max(0, t), min(img.width, r), min(img.height, b)))
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

    cols = cols or min(len(cells), 3)
    cols = max(1, min(int(cols), len(cells)))
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
        "{hotkey:['CTRL','KP_1']}, {orbit:[dx,dy]} (eased middle-drag orbit; ~250-330 px = a "
        "big swing), {move:[x,y]} (cursor INTO the viewport — include this before EACH orbit, "
        "the app orbits around the cursor area), {wait_ms:200}. Screenshots are full-window, so "
        "pass `crop:[left,top,right,bottom]` (the viewport bounds, from a prior screenshot) so "
        "the subject fills each tile, and/or frame the object large first. Optional `labels` "
        "(per view), `grid` (NxN ruler overlay), `cols` (montage columns), `settle_ms`. Returns the "
        "montage path, tile paths, and `distinct_views` — it auto-warns in `note` when tiles are "
        "pixel-identical (the orbit didn't register: move the cursor into the viewport and retry, "
        "or orbit via `act`). READ the montage to perceive the 3D structure."
    )
    args_help = ("views (list of step-lists; steps: {key}|{hotkey}|{orbit:[dx,dy]}|{move:[x,y]}|"
                 "{wait_ms}); optional labels (list[str]), grid (int NxN), crop ([l,t,r,b]), "
                 "cols (int), settle_ms (int)")
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
            self._orbit(dx, dy)
        elif "move" in step:
            x, y = self._point(step["move"], "move")
            ib.move(x, y)
        elif "wait_ms" in step:
            time.sleep(max(0, int(step["wait_ms"])) / 1000.0)
        else:
            raise ToolError(f"unknown view step {sorted(step)!r}; "
                            "allowed: key, hotkey, orbit, move, wait_ms")

    def _orbit(self, dx: int, dy: int, steps: int = 10,
               settle: float = 0.08, step_delay: float = 0.02) -> None:
        """Middle-drag orbit as an EASED, time-spaced motion.

        A single instantaneous jump while MMB is held is dropped by apps that
        integrate mouse-move deltas (Blender's GHOST layer) — the live finding
        (playbook blender-07). Holding the button, pausing, then moving in several
        small sub-steps with short sleeps emulates a real drag the app registers.
        """
        ib = self._input
        ib.mouse_down("middle")
        try:
            time.sleep(settle)  # let the button-down register before motion
            acc_x = acc_y = 0
            for i in range(1, steps + 1):
                tx, ty = round(dx * i / steps), round(dy * i / steps)
                mx, my = tx - acc_x, ty - acc_y
                acc_x, acc_y = tx, ty
                if mx or my:
                    ib.move_relative(mx, my)
                time.sleep(step_delay)
            time.sleep(settle)
        finally:
            ib.mouse_up("middle")

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
        crop = args.get("crop")
        if crop is not None:
            if not isinstance(crop, (list, tuple)) or len(crop) != 4:
                raise ToolError("crop must be [left, top, right, bottom]")
            try:
                crop = [int(v) for v in crop]
            except (TypeError, ValueError):
                raise ToolError("crop must be four integers")
            if crop[2] <= crop[0] or crop[3] <= crop[1]:
                raise ToolError("crop must have right>left and bottom>top")

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

        cols = args.get("cols")
        cols = int(cols) if cols else None

        # Sanity-check: pixel-identical tiles mean a view change (orbit) didn't
        # register — exactly the silent no-op that made the montage useless before.
        notes: list[str] = []
        digs = []
        for t in tiles:
            try:
                digs.append(hashlib.md5(Path(t).read_bytes()).hexdigest())
            except OSError:
                digs.append(None)
        real = [h for h in digs if h]
        distinct = len(set(real))
        if len(real) > 1 and distinct < len(real):
            notes.append("WARNING: some views are pixel-identical — the orbit/view change may "
                         "not have registered. Put a {move:[cx,cy]} into the viewport before each "
                         "{orbit}, increase the orbit delta, or orbit via an `act` MMB-drag.")

        montage = build_montage(tiles, labels, grid, self._work_dir / "inspect_montage.png",
                                crop=crop, cols=cols)
        if not montage:
            notes.append("montage skipped (Pillow missing or captures are not real images); "
                         "read the individual tile paths instead")
        return {"success": True, "montage": montage, "tiles": tiles,
                "labels": labels, "views": len(views), "distinct_views": distinct,
                "note": " | ".join(notes) or None, "error": None}
