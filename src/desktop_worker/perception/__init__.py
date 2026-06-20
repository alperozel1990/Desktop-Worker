"""Perception layer (requirements section 7).

Helps the AI understand what is on screen beyond raw pixels: structured UI
elements with bounds, confidence, and source attribution (uia / ocr / vision /
heuristic). UI Automation is the preferred source (DW-PERCEPTION-UIA); OCR and
vision are fallbacks.

The pure parser ``data_to_elements`` is dependency-free and unit-tested; the real
Tesseract backend imports pytesseract/PIL lazily and degrades to an empty result
when they are unavailable, so the loop never breaks for lack of OCR.
"""

from desktop_worker.perception.backends import (
    NullOcrBackend,
    OcrBackend,
    data_to_elements,
    get_ocr_backend,
)
from desktop_worker.perception.perceiver import Perceiver
from desktop_worker.perception.uia_backend import (
    NullUiaBackend,
    UiaBackend,
    control_to_type,
    get_uia_backend,
    merge_elements,
)

__all__ = [
    "OcrBackend",
    "NullOcrBackend",
    "data_to_elements",
    "get_ocr_backend",
    "Perceiver",
    "UiaBackend",
    "NullUiaBackend",
    "control_to_type",
    "merge_elements",
    "get_uia_backend",
]
