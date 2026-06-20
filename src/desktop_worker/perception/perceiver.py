"""Perceiver — enriches an observation with detected UI elements (req §7).

Takes an :class:`Observation` that already has a ``screenshotRef`` and returns a
NEW observation (Observation is frozen) with ``elements`` populated by the OCR
backend. If there is no usable screenshot, the observation is returned unchanged.

Future: a UIA backend (DW-PERCEPTION-UIA) will be merged here with UIA preferred
over OCR for the same region.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Optional

from desktop_worker.perception.backends import OcrBackend, get_ocr_backend
from desktop_worker.schema.observations import Element, Observation


class Perceiver:
    def __init__(self, ocr: Optional[OcrBackend] = None) -> None:
        self.ocr = ocr or get_ocr_backend()

    def detect(self, image_path: Path) -> list[Element]:
        return list(self.ocr.detect(Path(image_path)))

    def perceive(self, observation: Observation) -> Observation:
        """Return a copy of ``observation`` with detected elements attached."""
        ref = observation.screenshotRef
        if not ref:
            return observation
        path = Path(ref)
        # The Null desktop backend writes a .txt placeholder, not a real image;
        # only run OCR on actual image files so we never feed junk to Tesseract.
        if not path.exists() or path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".bmp"):
            return observation
        elements = tuple(self.ocr.detect(path))
        return dataclasses.replace(observation, elements=elements)
