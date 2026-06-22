"""Canvas detection — find Paint's REAL drawing area (the key to "controlled").

The old code guessed the canvas from the whole window rect, so strokes landed on
the ribbon or got clipped. This locator returns the actual drawing surface in
absolute screen pixels, UIA-first (per the §7 hard rule "prefer UI Automation
over image-only") with a deterministic geometric fallback that always works:

* **UIA** — walk the foreground window and pick the largest element that is
  inside the client area and is not a toolbar/menu/tab control. Works for both
  classic ``mspaint`` and the Win11 (UWP) Paint without hard-coding fragile
  names.
* **Client fallback** — compute the client area (``GetClientRect`` +
  ``ClientToScreen``, not the window rect, so the title bar/borders are excluded)
  and subtract *fractional* ribbon/status/side insets (DPI-relative).

The pure pieces (``CanvasRect``, ``client_to_canvas``, ``apply_inner_margin``)
are unit-tested without any window; ctypes/uiautomation/PIL are imported lazily.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Tuple, runtime_checkable

# Fractional insets for the geometric fallback (empirical, DPI-relative so they
# survive display scaling). The Paint ribbon+tabs occupy ~16% of client height.
_RIBBON_TOP = 0.16
_STATUS_BOTTOM = 0.05
_SIDE = 0.02
# Safety margin pulled in from the resolved rect so strokes never touch the very
# edge / scrollbars (applied to UIA hits too).
_INNER_MARGIN = 0.03

# UIA control types that are never the drawing canvas.
_NON_CANVAS = {"Button", "Menu", "MenuItem", "Tab", "TabItem", "ToolBar",
               "TitleBar", "ScrollBar", "Slider", "ComboBox", "CheckBox"}


@dataclass(frozen=True)
class CanvasRect:
    left: int
    top: int
    right: int
    bottom: int
    source: str  # "uia" | "client" | "null"

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def as_tuple(self) -> Tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)


def apply_inner_margin(rect: CanvasRect, frac: float = _INNER_MARGIN) -> CanvasRect:
    """Pull a rect inward by ``frac`` on each side (keeps strokes off the edge)."""
    dx, dy = rect.width * frac, rect.height * frac
    return CanvasRect(int(rect.left + dx), int(rect.top + dy),
                      int(rect.right - dx), int(rect.bottom - dy), rect.source)


def fit_square(rect: CanvasRect) -> CanvasRect:
    """Largest centered square inside ``rect`` (preserves aspect — circles stay round).

    The 0..100 grid maps x and y independently, so on a wide canvas a circle would
    render as a stretched ellipse. Drawing into a centered square fixes that; the
    figure is proportional and centered, with margins on the long axis.
    """
    side = min(rect.width, rect.height)
    cx, cy = (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2
    half = side // 2
    return CanvasRect(cx - half, cy - half, cx + half, cy + half, rect.source)


def client_to_canvas(client: Tuple[int, int, int, int]) -> CanvasRect:
    """Pure: client rect (screen px) -> drawing canvas, ribbon/status insets removed."""
    left, top, right, bottom = client
    w, h = right - left, bottom - top
    rect = CanvasRect(
        left=int(left + w * _SIDE),
        top=int(top + h * _RIBBON_TOP),
        right=int(right - w * _SIDE),
        bottom=int(bottom - h * _STATUS_BOTTOM),
        source="client",
    )
    return apply_inner_margin(rect)


@runtime_checkable
class CanvasLocator(Protocol):
    def locate(self) -> Optional[CanvasRect]:
        ...


class NullCanvasLocator:
    """Fixed deterministic canvas (tests / headless). No display needed."""

    def __init__(self, rect: Tuple[int, int, int, int] = (100, 100, 900, 700)) -> None:
        self._rect = CanvasRect(*rect, source="null")

    def locate(self) -> Optional[CanvasRect]:
        return self._rect


class WindowsCanvasLocator:
    """Real canvas detection: UIA-first, deterministic client fallback."""

    def __init__(self) -> None:
        import ctypes  # noqa: F401  (probe so the factory can fall back)

        self._ctypes = ctypes

    def locate(self) -> Optional[CanvasRect]:
        hwnd = self._ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return None
        client = self._client_rect(hwnd)
        if client is None:
            return None
        uia = self._uia_canvas(client)
        rect = apply_inner_margin(uia) if uia is not None else client_to_canvas(client)
        return rect

    # --- helpers -------------------------------------------------------
    def _client_rect(self, hwnd) -> Optional[Tuple[int, int, int, int]]:
        ctypes = self._ctypes
        user32 = ctypes.windll.user32

        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        r = RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(r)):
            return None
        origin = POINT(0, 0)
        user32.ClientToScreen(hwnd, ctypes.byref(origin))
        left, top = int(origin.x), int(origin.y)
        rect = (left, top, left + int(r.right), top + int(r.bottom))
        if rect[2] - rect[0] <= 0 or rect[3] - rect[1] <= 0:
            return None
        return rect

    def _uia_canvas(self, client: Tuple[int, int, int, int]) -> Optional[CanvasRect]:
        """Largest non-toolbar UIA element inside the client area, or None."""
        try:
            import ctypes

            import uiautomation as auto
        except Exception:
            return None
        cl, ct, cr, cb = client
        client_area = max(1, (cr - cl) * (cb - ct))
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            root = auto.ControlFromHandle(hwnd) if hwnd else None
        except Exception:
            root = None
        if root is None:
            return None

        best: Optional[CanvasRect] = None
        best_area = 0
        try:
            for control, _depth in auto.WalkControl(root, includeTop=False, maxDepth=12):
                try:
                    ctn = (control.ControlTypeName or "").replace("Control", "")
                    if ctn in _NON_CANVAS:
                        continue
                    rect = control.BoundingRectangle
                    if rect is None or rect.width() <= 0 or rect.height() <= 0:
                        continue
                    l, t, r, b = int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
                    # Must sit inside the client area (small tolerance).
                    if l < cl - 4 or t < ct - 4 or r > cr + 4 or b > cb + 4:
                        continue
                    area = (r - l) * (b - t)
                    # A real canvas covers a large share of the window.
                    if area > best_area and area >= 0.30 * client_area:
                        best_area = area
                        best = CanvasRect(l, t, r, b, source="uia")
                except Exception:
                    continue
        except Exception:
            return None
        return best


def get_canvas_locator(prefer_real: bool = True) -> CanvasLocator:
    """Return the best available canvas locator, falling back to Null."""
    if prefer_real:
        try:
            return WindowsCanvasLocator()
        except Exception:
            pass
    return NullCanvasLocator()


def crop_to_canvas(src: str, rect: CanvasRect, dest: str) -> Optional[str]:
    """Crop ``src`` PNG to the canvas rect (lazy PIL); None if PIL/crop unavailable."""
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return None
    try:
        with Image.open(src) as im:
            box = (max(0, rect.left), max(0, rect.top),
                   min(im.width, rect.right), min(im.height, rect.bottom))
            if box[2] <= box[0] or box[3] <= box[1]:
                return None
            im.crop(box).save(dest)
        return dest
    except Exception:
        return None
