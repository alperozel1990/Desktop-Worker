"""Windows UI Automation backend (requirements section 7 — the PREFERRED path).

Per §7: "Visual coordinate automation alone is not enough. Desktop-Worker must
use Windows UI Automation or Accessibility APIs where available, and use
screenshot/OCR/vision as fallback." This backend emits ``source="uia"`` elements
with real control types and exact bounds; OCR is merged in only where UIA has no
coverage (``merge_elements``, UIA preferred).

The control-type mapping (``control_to_type``) and the merge (``merge_elements``)
are pure, dependency-free, and unit-tested. The real ``WindowsUiaBackend`` imports
the ``uiautomation`` library lazily and degrades to an empty result if absent.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from desktop_worker.schema.observations import Element

# Map UIA ControlType names to Desktop-Worker element types (requirements §7).
_CONTROL_TYPE_MAP: dict[str, str] = {
    "Button": "button",
    "Edit": "input",
    "Document": "input",
    "CheckBox": "checkbox",
    "RadioButton": "radio",
    "ComboBox": "dropdown",
    "List": "list",
    "ListItem": "list",
    "Tab": "tab",
    "TabItem": "tab",
    "Menu": "menu",
    "MenuItem": "menu",
    "Hyperlink": "link",
    "Text": "text",
    "Image": "icon",
    "Table": "table",
    "DataGrid": "table",
    "Window": "window",
    "Pane": "pane",
}


def control_to_type(control_type_name: str) -> str:
    """Map a UIA ControlType name (e.g. 'ButtonControl' or 'Button') to our type."""
    name = (control_type_name or "").replace("Control", "")
    return _CONTROL_TYPE_MAP.get(name, "unknown")


def _center(bounds: tuple[int, int, int, int]) -> tuple[float, float]:
    left, top, right, bottom = bounds
    return (left + right) / 2.0, (top + bottom) / 2.0


def _contains(outer: tuple[int, int, int, int], point: tuple[float, float]) -> bool:
    left, top, right, bottom = outer
    x, y = point
    return left <= x <= right and top <= y <= bottom


def merge_elements(uia: list[Element], ocr: list[Element]) -> list[Element]:
    """Combine UIA and OCR elements with **UIA preferred**.

    Every UIA element is kept. An OCR element is kept only if its center does not
    fall inside any UIA element's bounds — i.e. OCR fills gaps UIA did not cover,
    and never duplicates a control UIA already reported (requirements §7).
    """
    merged: list[Element] = list(uia)
    for o in ocr:
        c = _center(o.bounds)
        if not any(_contains(u.bounds, c) for u in uia):
            merged.append(o)
    return merged


@runtime_checkable
class UiaBackend(Protocol):
    """Detects UI elements via Windows UI Automation."""

    def detect(self) -> list[Element]:
        ...


class NullUiaBackend:
    """No-op UIA backend (non-Windows or library absent)."""

    def detect(self) -> list[Element]:
        return []


class WindowsUiaBackend:
    """Real UIA via the ``uiautomation`` library. Construct only when available."""

    def __init__(self, *, max_elements: int = 200, max_depth: int = 12) -> None:
        import uiautomation  # noqa: F401  (probe so the factory can fall back)

        self.max_elements = max_elements
        self.max_depth = max_depth

    def detect(self) -> list[Element]:
        import ctypes

        import uiautomation as auto

        elements: list[Element] = []
        roots = []
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            fg = auto.ControlFromHandle(hwnd) if hwnd else None
            if fg is not None:
                roots.append(fg)
        except Exception:
            fg = None

        # Also include any OPEN context-menu / popup windows (class "#32768") so
        # the AI can see transient right-click menu items (New, Rename, ...). These
        # are top-level windows, not children of the foreground window.
        try:
            desktop = auto.GetRootControl()
            for child in desktop.GetChildren():
                try:
                    cls = child.ClassName or ""
                    ctn = child.ControlTypeName or ""
                    if "#32768" in cls or "Menu" in ctn:
                        roots.append(child)
                except Exception:
                    continue
        except Exception:
            pass

        if not roots:
            return []

        count = 0
        for root in roots:
            for control, _depth in auto.WalkControl(root, includeTop=True, maxDepth=self.max_depth):
                if count >= self.max_elements:
                    break
                try:
                    rect = control.BoundingRectangle
                    if rect is None or rect.width() <= 0 or rect.height() <= 0:
                        continue
                    bounds = (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
                    etype = control_to_type(control.ControlTypeName)
                    name = control.Name or None
                    text = name
                    # For editable controls, also read the current VALUE so the AI
                    # can SEE what it has typed (feedback that input landed).
                    if etype in ("input", "dropdown"):
                        try:
                            v = control.GetValuePattern().Value
                            if v:
                                text = f"{name}: {v}" if name else v
                        except Exception:
                            pass
                    # Skip unnamed, valueless generic panes/text (noise).
                    if text is None and etype in ("pane", "unknown", "window", "text"):
                        continue
                    elements.append(Element(
                        id=f"uia-{count}", type=etype, bounds=bounds,
                        source="uia", text=text, label=name, confidence=0.99,
                    ))
                    count += 1
                except Exception:
                    continue
        return elements


def get_uia_backend(prefer_real: bool = True) -> UiaBackend:
    """Return the best available UIA backend, falling back to Null."""
    if prefer_real:
        try:
            return WindowsUiaBackend()
        except Exception:
            pass
    return NullUiaBackend()
