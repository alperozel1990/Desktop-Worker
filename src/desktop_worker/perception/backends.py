"""OCR backends behind a Protocol (requirements section 7).

`data_to_elements` is a PURE function that converts pytesseract's
``image_to_data(output_type=DICT)`` mapping into structured :class:`Element`s, so
the parsing logic is fully unit-testable without Tesseract installed. The real
:class:`TesseractOcrBackend` only adds the lazy image-loading + tesseract call.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from desktop_worker.schema.observations import Element


@runtime_checkable
class OcrBackend(Protocol):
    """Detects text elements in a screenshot image."""

    def detect(self, image_path: Path) -> list[Element]:
        ...


class NullOcrBackend:
    """No-op OCR backend (no Tesseract). Keeps the loop working without OCR."""

    def detect(self, image_path: Path) -> list[Element]:
        return []


def data_to_elements(data: dict[str, Any], *, min_confidence: float = 0.0) -> list[Element]:
    """Convert a pytesseract ``image_to_data`` DICT into :class:`Element`s.

    Expects parallel lists under keys: ``text``, ``conf``, ``left``, ``top``,
    ``width``, ``height``. Blank text and entries below ``min_confidence`` (0..1)
    are dropped. Tesseract reports confidence as 0..100 (or -1 for "no text");
    we normalize to 0..1.
    """
    texts = data.get("text", [])
    confs = data.get("conf", [])
    lefts = data.get("left", [])
    tops = data.get("top", [])
    widths = data.get("width", [])
    heights = data.get("height", [])

    elements: list[Element] = []
    n = min(len(texts), len(confs), len(lefts), len(tops), len(widths), len(heights))
    for i in range(n):
        text = (texts[i] or "").strip()
        if not text:
            continue
        try:
            raw_conf = float(confs[i])
        except (TypeError, ValueError):
            raw_conf = -1.0
        if raw_conf < 0:
            continue
        confidence = raw_conf / 100.0
        if confidence < min_confidence:
            continue
        left, top = int(lefts[i]), int(tops[i])
        right, bottom = left + int(widths[i]), top + int(heights[i])
        # ID counts EMITTED elements so they are contiguous (ocr-0, ocr-1, ...)
        # even when leading raw entries were filtered out.
        elements.append(Element(
            id=f"ocr-{len(elements)}", type="text", text=text,
            bounds=(left, top, right, bottom),
            source="ocr", confidence=round(confidence, 3),
        ))
    return elements


class TesseractOcrBackend:
    """Real OCR via pytesseract + Pillow. Construct only when both are present."""

    def __init__(self, *, min_confidence: float = 0.3) -> None:
        import pytesseract  # noqa: F401  (probe so the factory can fall back)
        from PIL import Image  # noqa: F401

        self.min_confidence = min_confidence

    def detect(self, image_path: Path) -> list[Element]:
        import pytesseract
        from PIL import Image

        image_path = Path(image_path)
        if not image_path.exists():
            return []
        with Image.open(image_path) as img:
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        return data_to_elements(data, min_confidence=self.min_confidence)


def get_ocr_backend(prefer_real: bool = True) -> OcrBackend:
    """Return the best available OCR backend, falling back to Null."""
    if prefer_real:
        try:
            return TesseractOcrBackend()
        except Exception:
            pass
    return NullOcrBackend()
