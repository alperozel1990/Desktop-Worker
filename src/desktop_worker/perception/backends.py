"""OCR backends behind a Protocol (requirements section 7).

`data_to_elements` is a PURE function that converts pytesseract's
``image_to_data(output_type=DICT)`` mapping into structured :class:`Element`s, so
the parsing logic is fully unit-testable without Tesseract installed. The real
:class:`TesseractOcrBackend` only adds the lazy image-loading + tesseract call.
"""

from __future__ import annotations

import os
import shutil
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


def _well_known_tesseract_dirs() -> list[Path]:
    """Default install locations the tesseract installer commonly writes to,
    checked when neither TESSERACT_CMD nor PATH resolve the binary.

    Prefers the ``ProgramFiles`` / ``ProgramFiles(x86)`` env vars when present,
    but a child process spawned with a sanitized/minimal environment (e.g.
    Autonom's managed worker spawn, which passes only SystemRoot, SystemDrive,
    PATHEXT, COMSPEC, TEMP, TMP, USERPROFILE) carries neither. In that case
    derive the same default roots from ``SystemDrive``, since "Program Files"
    lives there on any standard Windows install.
    """
    dirs: list[Path] = []
    program_files_vars = ("ProgramFiles", "ProgramFiles(x86)")
    for var in program_files_vars:
        base = os.environ.get(var)
        if base:
            dirs.append(Path(base) / "Tesseract-OCR")

    if not any(os.environ.get(var) for var in program_files_vars):
        system_drive = os.environ.get("SystemDrive")
        if system_drive:
            # Path(system_drive) alone (e.g. "C:") is drive-RELATIVE on
            # Windows pathlib -- it resolves against that drive's CWD, not
            # its root. Appending os.sep forces an absolute anchor ("C:\\").
            drive_root = Path(system_drive + os.sep)
            for suffix in ("Program Files", "Program Files (x86)"):
                dirs.append(drive_root / suffix / "Tesseract-OCR")

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        dirs.append(Path(local_app_data) / "Programs" / "Tesseract-OCR")
    return dirs


def resolve_tesseract_cmd() -> str | None:
    """Resolve the tesseract binary path without relying on an inherited PATH.

    A child process spawned with a minimal/sanitized environment (e.g. the MCP
    server under a headless launcher) may have NO PATH at all, so
    ``pytesseract.get_tesseract_version()`` — which shells out to a bare
    ``tesseract`` — fails even though the binary is installed. Resolve it
    ourselves first, in order of trust:

    1. ``TESSERACT_CMD`` env var, if set (explicit operator override; used
       verbatim so a bad value fails loudly rather than being silently
       skipped).
    2. ``shutil.which('tesseract')`` (works whenever PATH IS present).
    3. Well-known default install directories the Windows installer uses.

    Returns ``None`` when nothing is found, so the caller can fail closed.
    """
    explicit = os.environ.get("TESSERACT_CMD")
    if explicit:
        return explicit

    found = shutil.which("tesseract")
    if found:
        return found

    for d in _well_known_tesseract_dirs():
        candidate = d / "tesseract.exe"
        if candidate.is_file():
            return str(candidate)

    return None


class TesseractOcrBackend:
    """Real OCR via pytesseract + Pillow. Construct only when both are present.

    The constructor probes not just the Python bindings but the tesseract BINARY,
    because a bindings-present / binary-absent install is common (the installer
    often skips PATH). Without that probe, the factory would happily return this
    backend and the first ``detect`` would raise ``TesseractNotFoundError`` and
    crash the whole perceive — turning a degraded read into a hard failure.
    """

    def __init__(self, *, min_confidence: float = 0.3) -> None:
        import pytesseract
        from PIL import Image  # noqa: F401

        cmd = resolve_tesseract_cmd()
        if cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd

        # Fail construction (not detect) when the binary is missing, so the factory
        # can fall back to Null and perception keeps working, just thinner.
        pytesseract.get_tesseract_version()
        self.min_confidence = min_confidence

    def detect(self, image_path: Path) -> list[Element]:
        import pytesseract
        from PIL import Image

        image_path = Path(image_path)
        if not image_path.exists():
            return []
        try:
            with Image.open(image_path) as img:
                data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        except pytesseract.TesseractNotFoundError:
            # The binary disappeared after construction (PATH changed mid-session).
            # A missing OCR binary must never crash perceive — degrade to no OCR.
            return []
        return data_to_elements(data, min_confidence=self.min_confidence)


def get_ocr_backend(prefer_real: bool = True) -> OcrBackend:
    """Return the best available OCR backend, falling back to Null."""
    if prefer_real:
        try:
            return TesseractOcrBackend()
        except Exception:
            pass
    return NullOcrBackend()


def ocr_status() -> dict[str, Any]:
    """Report whether OCR is actually usable, and WHY not if it is not.

    This exists because a missing OCR stack does not fail loudly — it just makes
    perception quietly thinner. On EDA / wxWidgets apps that is dangerous: KiCad
    draws ~76% of its elements via OCR, so without Tesseract it perceives 46
    elements instead of 193 — a 4x undercount that looks like a perfectly healthy
    result. An agent cannot tell "this control does not exist" from "OCR is off and
    I never saw it". Surfacing the health lets a caller refuse to trust a thin read.

    Checks all three pieces the real backend needs: pytesseract (Python binding),
    Pillow (image loading), and the tesseract BINARY on PATH (the piece the
    installer commonly forgets to add).
    """
    missing: list[str] = []
    version = None
    try:
        import pytesseract  # noqa: F401
    except Exception:
        missing.append("pytesseract")
    try:
        from PIL import Image  # noqa: F401
    except Exception:
        missing.append("Pillow")

    if "pytesseract" not in missing:
        try:
            import pytesseract

            cmd = resolve_tesseract_cmd()
            if cmd:
                pytesseract.pytesseract.tesseract_cmd = cmd
            version = str(pytesseract.get_tesseract_version())
        except Exception:
            # The binding is installed but the tesseract EXE is not on PATH — the
            # single most common broken state (winget does not add it to PATH).
            missing.append("tesseract-binary")

    available = not missing
    if available:
        reason = f"OCR ready (tesseract {version})"
    elif missing == ["tesseract-binary"]:
        reason = (
            "pytesseract is installed but the tesseract executable is not on PATH; "
            "add its install dir (e.g. C:\\Program Files\\Tesseract-OCR) to PATH"
        )
    else:
        reason = (
            "OCR unavailable — install the [ocr] extra and Tesseract "
            f"(missing: {', '.join(missing)})"
        )
    return {
        "available": available,
        "backend": "tesseract" if available else "null",
        "version": version,
        "missing": missing,
        "reason": reason,
    }
