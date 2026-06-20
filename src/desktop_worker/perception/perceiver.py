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
from desktop_worker.perception.uia_backend import (
    UiaBackend,
    get_uia_backend,
    merge_elements,
)
from desktop_worker.schema.observations import Element, Observation

_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp")


class Perceiver:
    """Builds structured elements, preferring UIA and falling back to OCR (§7)."""

    def __init__(
        self,
        ocr: Optional[OcrBackend] = None,
        uia: Optional[UiaBackend] = None,
    ) -> None:
        self.ocr = ocr or get_ocr_backend()
        self.uia = uia or get_uia_backend()

    def detect(self, image_path: Path) -> list[Element]:
        """OCR-detect elements in a specific image (used standalone)."""
        return list(self.ocr.detect(Path(image_path)))

    def perceive(self, observation: Observation) -> Observation:
        """Return a copy of ``observation`` enriched with detected elements.

        UIA elements (preferred) are gathered first; OCR runs only on a real
        screenshot image and is merged in to fill gaps UIA did not cover.
        """
        uia_elements = list(self.uia.detect())

        ocr_elements: list[Element] = []
        ref = observation.screenshotRef
        if ref:
            path = Path(ref)
            # The Null desktop backend writes a .txt placeholder, not a real
            # image; only OCR actual images so we never feed junk to Tesseract.
            if path.exists() and path.suffix.lower() in _IMAGE_SUFFIXES:
                ocr_elements = list(self.ocr.detect(path))

        if not uia_elements and not ocr_elements:
            return observation
        elements = tuple(merge_elements(uia_elements, ocr_elements))
        return dataclasses.replace(observation, elements=elements)
