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


# Ranking tiers for truncation (DW-PERCEIVE-RANK). When more controls exist than
# fit in the budget, keep the ones an agent can ACT on. Cutting in tree-traversal
# order — as the previous implementation did — drops whatever happens to sit late
# in the walk, which on a dense UI is frequently the target button.
_INTERACTABLE = ("button", "input", "checkbox", "radio", "dropdown", "menu", "tab", "link")
_SECONDARY = ("list", "table", "icon")


def rank_key(element: Element) -> tuple[int, int]:
    """Sort key: interactable first, then structural, then static text.

    Returns ``(tier, 0)``; callers pair it with the element's original index so
    the sort stays stable and, within a tier, traversal order is preserved.
    """
    etype = element.type
    if etype in _INTERACTABLE:
        tier = 0
    elif etype in _SECONDARY:
        tier = 1
    elif etype == "text":
        tier = 3
    else:
        tier = 2
    return (tier, 0)


def rank_and_cap(
    elements: list[Element], max_elements: int
) -> tuple[list[Element], dict[str, object]]:
    """Rank interactable-first and cap, reporting exactly what was dropped.

    The report is the point: an agent must be able to tell "that control does not
    exist" from "you were not told about it". Silent truncation makes those two
    indistinguishable.
    """
    total = len(elements)
    ordered = sorted(enumerate(elements), key=lambda pair: (rank_key(pair[1]), pair[0]))
    kept = [element for _index, element in ordered[:max_elements]]
    dropped = ordered[max_elements:]
    dropped_by_type: dict[str, int] = {}
    for _index, element in dropped:
        dropped_by_type[element.type] = dropped_by_type.get(element.type, 0) + 1
    return kept, {
        "truncated": bool(dropped),
        "totalSeen": total,
        "returned": len(kept),
        "dropped": len(dropped),
        "droppedByType": dropped_by_type,
    }


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

    def __init__(
        self, *, max_elements: int = 200, max_depth: int = 12, hard_cap: int = 1200
    ) -> None:
        import uiautomation  # noqa: F401  (probe so the factory can fall back)

        self.max_elements = max_elements
        self.max_depth = max_depth
        # Walk beyond max_elements so ranking has candidates to choose FROM; the
        # hard cap only stops a pathological tree from walking forever.
        self.hard_cap = max(hard_cap, max_elements)

    def detect(self) -> list[Element]:
        """Elements only — the stable :class:`UiaBackend` protocol method."""
        return self.detect_detailed()[0]

    def detect_detailed(self) -> tuple[list[Element], dict[str, object]]:
        """Elements plus a truncation report.

        Additive on purpose: the ``UiaBackend`` protocol (and every Null backend
        and test that implements it) keeps working through :meth:`detect`, while
        callers that want to know what was dropped can ask for it.
        """
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
            return [], {"truncated": False, "totalSeen": 0, "returned": 0, "dropped": 0,
                        "droppedByType": {}}

        count = 0
        hit_hard_cap = False
        for root in roots:
            for control, _depth in auto.WalkControl(root, includeTop=True, maxDepth=self.max_depth):
                if count >= self.hard_cap:
                    hit_hard_cap = True
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

        kept, report = rank_and_cap(elements, self.max_elements)
        if hit_hard_cap:
            report["hitHardCap"] = True
            report["hardCap"] = self.hard_cap
        return kept, report


def get_uia_backend(prefer_real: bool = True) -> UiaBackend:
    """Return the best available UIA backend, falling back to Null."""
    if prefer_real:
        try:
            return WindowsUiaBackend()
        except Exception:
            pass
    return NullUiaBackend()
