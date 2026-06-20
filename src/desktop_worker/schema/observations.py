"""Structured observation schema (requirements section 6).

Observation output is always structured so the AI receives stable, parseable
desktop state plus a screenshot reference for vision-capable models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from desktop_worker.util import utc_now_iso


@dataclass(frozen=True)
class Screen:
    width: int
    height: int
    scaleFactor: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {"width": self.width, "height": self.height, "scaleFactor": self.scaleFactor}


@dataclass(frozen=True)
class Cursor:
    x: int
    y: int

    def to_dict(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y}


@dataclass(frozen=True)
class Element:
    """A detected on-screen UI element (requirements section 7).

    ``source`` attributes where the element came from: "uia" (Windows UI
    Automation, preferred), "ocr", "vision", or "heuristic". ``bounds`` is
    (left, top, right, bottom) in screen pixels.
    """

    id: str
    type: str  # button, input, text, checkbox, link, ...
    bounds: tuple[int, int, int, int]
    source: str = "ocr"
    text: Optional[str] = None
    label: Optional[str] = None
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "bounds": list(self.bounds),
            "source": self.source,
            "text": self.text,
            "label": self.label,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class ActiveWindow:
    title: str
    process: str
    bounds: tuple[int, int, int, int]  # left, top, right, bottom

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "process": self.process, "bounds": list(self.bounds)}


@dataclass(frozen=True)
class Observation:
    """A structured snapshot of desktop state at a point in time."""

    screen: Screen
    cursor: Cursor
    activeWindow: Optional[ActiveWindow] = None
    screenshotRef: Optional[str] = None
    timestamp: str = field(default_factory=utc_now_iso)
    # Visible windows (title list) — single-monitor MVP keeps this simple.
    windows: tuple[str, ...] = ()
    # Detected UI elements (Perception layer, requirements §7). Empty until a
    # perception backend (OCR/UIA) enriches the observation.
    elements: tuple[Element, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "screen": self.screen.to_dict(),
            "cursor": self.cursor.to_dict(),
            "activeWindow": self.activeWindow.to_dict() if self.activeWindow else None,
            "screenshotRef": self.screenshotRef,
            "windows": list(self.windows),
            "elements": [e.to_dict() for e in self.elements],
        }

    def summary(self) -> str:
        """Compact human/AI-readable one-liner for prompts and logs."""
        aw = self.activeWindow
        win = f"{aw.title!r} ({aw.process})" if aw else "unknown"
        return (
            f"screen={self.screen.width}x{self.screen.height} "
            f"cursor=({self.cursor.x},{self.cursor.y}) active={win}"
        )
