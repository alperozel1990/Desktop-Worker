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

    OCR words are single-token, so any multi-word or phrase-anchored selector
    ('New Run', a window title, ...) can never match a word element. To make
    those selectors matchable, surviving words are ALSO grouped by their
    ``(block_num, par_num, line_num)`` (the line-grouping keys pytesseract
    already reports per row) into line-level elements: text is the words
    joined in reading order, bounds is the union of the word bounds, and
    confidence is the mean of the word confidences. Line elements are
    appended after the word elements (source ``"ocr-line"`` vs ``"ocr"``) so
    callers that rely on the existing word list are unaffected.
    """
    texts = data.get("text", [])
    confs = data.get("conf", [])
    lefts = data.get("left", [])
    tops = data.get("top", [])
    widths = data.get("width", [])
    heights = data.get("height", [])
    block_nums = data.get("block_num", [])
    par_nums = data.get("par_num", [])
    line_nums = data.get("line_num", [])

    elements: list[Element] = []
    line_order: list[tuple[int, int, int]] = []
    line_words: dict[tuple[int, int, int], list[tuple[str, float, int, int, int, int]]] = {}
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

        # Rows missing block/par/line_num (hand-built dicts) fall back to a
        # single shared line (0, 0, 0), so they still group deterministically.
        line_key = (
            int(block_nums[i]) if i < len(block_nums) else 0,
            int(par_nums[i]) if i < len(par_nums) else 0,
            int(line_nums[i]) if i < len(line_nums) else 0,
        )
        if line_key not in line_words:
            line_words[line_key] = []
            line_order.append(line_key)
        line_words[line_key].append((text, confidence, left, top, right, bottom))

    line_elements: list[Element] = []
    for line_key in line_order:
        words = line_words[line_key]
        line_text = " ".join(w[0] for w in words)
        line_confidence = sum(w[1] for w in words) / len(words)
        line_left = min(w[2] for w in words)
        line_top = min(w[3] for w in words)
        line_right = max(w[4] for w in words)
        line_bottom = max(w[5] for w in words)
        line_elements.append(Element(
            id=f"ocr-line-{len(line_elements)}", type="text", text=line_text,
            bounds=(line_left, line_top, line_right, line_bottom),
            source="ocr-line", confidence=round(line_confidence, 3),
        ))

    return elements + line_elements


def _ocr_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Explode a pytesseract DICT into row dicts, index-aligned like `data_to_elements`.

    Missing block/par/line_num fall back to 0, matching `data_to_elements`'s
    single-shared-line fallback for hand-built dicts.
    """
    texts = data.get("text", [])
    confs = data.get("conf", [])
    lefts = data.get("left", [])
    tops = data.get("top", [])
    widths = data.get("width", [])
    heights = data.get("height", [])
    block_nums = data.get("block_num", [])
    par_nums = data.get("par_num", [])
    line_nums = data.get("line_num", [])
    n = min(len(texts), len(confs), len(lefts), len(tops), len(widths), len(heights))
    rows = []
    for i in range(n):
        rows.append({
            "text": texts[i], "conf": confs[i],
            "left": lefts[i], "top": tops[i], "width": widths[i], "height": heights[i],
            "block_num": int(block_nums[i]) if i < len(block_nums) else 0,
            "par_num": int(par_nums[i]) if i < len(par_nums) else 0,
            "line_num": int(line_nums[i]) if i < len(line_nums) else 0,
        })
    return rows


def _row_text_conf_bounds(row: dict[str, Any]) -> tuple[str, float, tuple[int, int, int, int]]:
    text = (row["text"] or "").strip()
    try:
        conf = float(row["conf"])
    except (TypeError, ValueError):
        conf = -1.0
    left, top = int(row["left"]), int(row["top"])
    right, bottom = left + int(row["width"]), top + int(row["height"])
    return text, conf, (left, top, right, bottom)


def _bounds_overlap(
    a: tuple[int, int, int, int], b: tuple[int, int, int, int], *,
    iou_threshold: float = 0.3, center_distance_ratio: float = 0.5,
) -> bool:
    """True if two boxes are "the same word" spatially: IoU above threshold, OR
    (fallback, for slightly mismatched OCR boxes around the same glyphs) their
    centers are close relative to the larger box's size."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    inter_w = max(0, min(ax1, bx1) - max(ax0, bx0))
    inter_h = max(0, min(ay1, by1) - max(ay0, by0))
    inter_area = inter_w * inter_h
    area_a = max(0, ax1 - ax0) * max(0, ay1 - ay0)
    area_b = max(0, bx1 - bx0) * max(0, by1 - by0)
    union = area_a + area_b - inter_area
    if union > 0 and inter_area / union >= iou_threshold:
        return True
    ax_c, ay_c = (ax0 + ax1) / 2, (ay0 + ay1) / 2
    bx_c, by_c = (bx0 + bx1) / 2, (by0 + by1) / 2
    dist = ((ax_c - bx_c) ** 2 + (ay_c - by_c) ** 2) ** 0.5
    max_dim = max(ax1 - ax0, ay1 - ay0, bx1 - bx0, by1 - by0, 1)
    return dist <= max_dim * center_distance_ratio


def merge_ocr_passes(data_normal: dict[str, Any], data_inverted: dict[str, Any]) -> dict[str, Any]:
    """Merge a normal-polarity and an inverted-polarity `image_to_data` DICT.

    A word from the inverted pass is dropped as a duplicate of a normal-pass
    word when both are non-blank, case-insensitively equal text AND spatially
    overlapping (`_bounds_overlap`); the lower-confidence side of the pair is
    dropped, the other kept as-is. Everything else from both passes survives
    untouched. The inverted pass's `block_num` is offset past the normal
    pass's range first, so `data_to_elements`'s (block, par, line) line
    grouping never accidentally fuses a normal-pass line with an
    inverted-pass line that happens to share the same raw numbering.

    When one pass is empty (e.g. hand-built single-polarity test dicts, or a
    real pass that found nothing), the merge is a no-op that reproduces the
    other pass's rows unchanged -- single-polarity callers see no behavior
    change.
    """
    rows_a = _ocr_rows(data_normal)
    rows_b = _ocr_rows(data_inverted)

    block_offset = max((r["block_num"] for r in rows_a), default=-1) + 1
    for row in rows_b:
        row["block_num"] += block_offset

    infos_a = [_row_text_conf_bounds(r) for r in rows_a]
    dropped_a: set[int] = set()
    kept_b: list[dict[str, Any]] = []
    for row_b in rows_b:
        text_b, conf_b, bounds_b = _row_text_conf_bounds(row_b)
        dup_index = None
        if text_b:
            for idx, (text_a, _conf_a, bounds_a) in enumerate(infos_a):
                if idx in dropped_a or not text_a or text_a.lower() != text_b.lower():
                    continue
                if _bounds_overlap(bounds_a, bounds_b):
                    dup_index = idx
                    break
        if dup_index is None:
            kept_b.append(row_b)
            continue
        conf_a = infos_a[dup_index][1]
        if conf_b > conf_a:
            dropped_a.add(dup_index)
            kept_b.append(row_b)
        # else: pass A's row wins and is kept below; this pass B row is dropped.

    merged_rows = [r for i, r in enumerate(rows_a) if i not in dropped_a] + kept_b
    return {
        "text": [r["text"] for r in merged_rows],
        "conf": [r["conf"] for r in merged_rows],
        "left": [r["left"] for r in merged_rows],
        "top": [r["top"] for r in merged_rows],
        "width": [r["width"] for r in merged_rows],
        "height": [r["height"] for r in merged_rows],
        "block_num": [r["block_num"] for r in merged_rows],
        "par_num": [r["par_num"] for r in merged_rows],
        "line_num": [r["line_num"] for r in merged_rows],
    }


def _resolve_crop_box(
    image_size: tuple[int, int],
    window_bounds: tuple[int, int, int, int] | None,
    *,
    pad: int = 8,
) -> tuple[int, int, int, int] | None:
    """Pad and clamp `window_bounds` into a valid PIL crop box within `image_size`.

    Returns ``None`` (never raises) when `window_bounds` is missing or
    degenerate -- not a 4-tuple, non-numeric, zero/negative width or height,
    or a box that clamps to zero area (e.g. bounds entirely outside the
    screenshot) -- so the caller can fail closed and skip the crop pass.
    """
    if not window_bounds or len(window_bounds) != 4:
        return None
    try:
        left, top, right, bottom = (int(v) for v in window_bounds)
    except (TypeError, ValueError):
        return None
    if right <= left or bottom <= top:
        return None
    img_w, img_h = image_size
    left = max(0, left - pad)
    top = max(0, top - pad)
    right = min(img_w, right + pad)
    bottom = min(img_h, bottom + pad)
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _offset_ocr_data(data: dict[str, Any], dx: int, dy: int) -> dict[str, Any]:
    """Return a copy of `data` with `left`/`top` shifted by `(dx, dy)`.

    Used to translate a crop-region OCR pass's coordinates (relative to the
    crop) back into full-screenshot/screen coordinates before merging.
    """
    shifted = dict(data)
    shifted["left"] = [int(v) + dx for v in data.get("left", [])]
    shifted["top"] = [int(v) + dy for v in data.get("top", [])]
    return shifted


DEFAULT_SPARSE_THRESHOLD = 20
DEFAULT_TILE_GRID: tuple[int, int] = (3, 2)
DEFAULT_TILE_OVERLAP = 0.1
DEFAULT_THRESHOLD_LEVELS: tuple[int, ...] = (120, 170)


def _tile_boxes(
    image_size: tuple[int, int],
    *,
    grid: tuple[int, int] = DEFAULT_TILE_GRID,
    overlap: float = DEFAULT_TILE_OVERLAP,
) -> list[tuple[int, int, int, int]]:
    """Compute a grid of overlapping tile boxes covering `image_size`.

    `grid` is `(cols, rows)`. Each cell of the base grid is expanded by
    `overlap` (a fraction of that cell's own width/height) on every side,
    then clamped into the image -- so tiles bordering the same seam share a
    strip of pixels wide enough that a word straddling the base grid line
    lands whole inside at least one tile. Boxes are returned row-major
    (all of row 0 left-to-right, then row 1, ...).

    Returns an empty list for a degenerate `image_size` or `grid` (<=0 in
    any dimension) so callers can skip the pass rather than OCR-ing
    zero-area crops.
    """
    img_w, img_h = image_size
    cols, rows = grid
    if img_w <= 0 or img_h <= 0 or cols <= 0 or rows <= 0:
        return []
    base_w = img_w / cols
    base_h = img_h / rows
    pad_w = base_w * overlap
    pad_h = base_h * overlap
    boxes: list[tuple[int, int, int, int]] = []
    for r in range(rows):
        for c in range(cols):
            left = max(0, c * base_w - pad_w)
            top = max(0, r * base_h - pad_h)
            right = min(img_w, (c + 1) * base_w + pad_w)
            bottom = min(img_h, (r + 1) * base_h + pad_h)
            box = (int(left), int(top), int(right), int(bottom))
            if box[2] > box[0] and box[3] > box[1]:
                boxes.append(box)
    return boxes


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

    def __init__(
        self,
        *,
        min_confidence: float = 0.3,
        sparse_threshold: int = DEFAULT_SPARSE_THRESHOLD,
        tile_grid: tuple[int, int] = DEFAULT_TILE_GRID,
        tile_overlap: float = DEFAULT_TILE_OVERLAP,
        threshold_levels: tuple[int, ...] = DEFAULT_THRESHOLD_LEVELS,
    ) -> None:
        import pytesseract
        from PIL import Image  # noqa: F401

        cmd = resolve_tesseract_cmd()
        if cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd

        # Fail construction (not detect) when the binary is missing, so the factory
        # can fall back to Null and perception keeps working, just thinner.
        pytesseract.get_tesseract_version()
        self.min_confidence = min_confidence
        self.sparse_threshold = sparse_threshold
        self.tile_grid = tile_grid
        self.tile_overlap = tile_overlap
        self.threshold_levels = threshold_levels

    @staticmethod
    def _dual_polarity_data(img: Any) -> dict[str, Any]:
        """Run OCR on `img` AND an inverted copy, merged via `merge_ocr_passes`.

        Tesseract binarizes per image, not per region: a small light-on-dark
        (or dark-on-light) island inside a screen that is mostly the opposite
        polarity is often read as noise and dropped entirely, even though it
        is clearly legible (proven live: a light tkinter window on a dark
        terminal returned zero words from inside the window). Running a
        second pass on `ImageOps.invert`-ed RGB recovers those words;
        `merge_ocr_passes` dedupes anything both passes already agree on.
        This roughly DOUBLES OCR cost per screenshot (two full
        `image_to_data` calls) -- acceptable here since perceive already
        pays for a screenshot + UIA walk, but worth knowing if this backend
        is ever called in a tight loop.
        """
        import pytesseract
        from PIL import ImageOps

        data_normal = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        inverted = ImageOps.invert(img.convert("RGB"))
        data_inverted = pytesseract.image_to_data(inverted, output_type=pytesseract.Output.DICT)
        return merge_ocr_passes(data_normal, data_inverted)

    def _tiled_data(self, img: Any) -> dict[str, Any]:
        """Run the dual-polarity pass on each tile of an overlapping grid over `img`.

        Tesseract's page segmentation is tuned for page-scale layouts: on a
        sparse fullscreen UI (mostly one flat color, a few small text
        islands) it under-segments and drops legible text that a smaller
        crop would read cleanly -- proven live on a 1920x1200 dark game
        screen where two large, clearly-legible buttons were missed by both
        the full-screen pass and a crop of the (identical, fullscreen)
        active window. Splitting into overlapping tiles gives each text
        island a page-scale-relative context small enough to segment
        correctly. Each tile reuses `_dual_polarity_data` (normal + inverted)
        so a light-on-dark button inside a tile still gets both polarities.
        Tile results are merged pairwise via `merge_ocr_passes`, which both
        offsets away any (block, par, line) collisions between tiles AND
        dedupes words that land in more than one tile's overlap region
        (keeping the higher-confidence read). A tile whose OCR call raises
        is skipped -- one bad crop must never blank out the whole pass.
        """
        merged_tiles: dict[str, Any] = {
            "text": [], "conf": [], "left": [], "top": [], "width": [], "height": [],
            "block_num": [], "par_num": [], "line_num": [],
        }
        for left, top, right, bottom in _tile_boxes(
            img.size, grid=self.tile_grid, overlap=self.tile_overlap
        ):
            try:
                tile_data = self._dual_polarity_data(img.crop((left, top, right, bottom)))
            except Exception:
                continue
            merged_tiles = merge_ocr_passes(merged_tiles, _offset_ocr_data(tile_data, left, top))
        return merged_tiles

    @staticmethod
    def _binarized_data(img: Any, level: int) -> dict[str, Any]:
        """OCR a single fixed-threshold binarization of `img` at `level` (0..255).

        Otsu's per-image auto-threshold (what plain/dual-polarity OCR relies
        on) picks ONE split point for the whole image; a mid-luminance solid
        UI block with white text on it (e.g. a blue "New Run" button) often
        lands on the wrong side of that split and gets lumped in with its own
        text, erasing it -- proven live on the DND home screen, where the
        full pass, dual-polarity pass, PSM 11, and the tiled pass all missed
        "New Run" and "Settings". A simple grayscale binarization at ANY
        fixed level in roughly 100..200 reads those buttons cleanly, because
        the fixed level does not adapt (wrongly) to the rest of the image the
        way Otsu does. This is a generic fix (any mid-luminance block, not
        this specific screenshot) precisely because no single Otsu split can
        be right for every block color on a screen -- a fixed level sidesteps
        the adaptivity that causes the failure.
        """
        import pytesseract

        gray = img.convert("L")
        binarized = gray.point(lambda p, _level=level: 255 if p > _level else 0)
        return pytesseract.image_to_data(binarized, output_type=pytesseract.Output.DICT)

    def _threshold_pass_data(self, img: Any) -> dict[str, Any]:
        """Run `_binarized_data` at each of `self.threshold_levels`, merged.

        Two fixed levels (default 120 and 170) bracket the "any threshold in
        100..200 works" band measured live, so between them they cover
        mid-luminance blocks of either a slightly darker or slightly lighter
        shade without needing per-image calibration. A level whose OCR call
        raises is skipped -- one bad binarization must never blank out the
        whole pass.
        """
        merged: dict[str, Any] = {
            "text": [], "conf": [], "left": [], "top": [], "width": [], "height": [],
            "block_num": [], "par_num": [], "line_num": [],
        }
        for level in self.threshold_levels:
            try:
                data = self._binarized_data(img, level)
            except Exception:
                continue
            merged = merge_ocr_passes(merged, data)
        return merged

    def _maybe_add_sparse_passes(self, img: Any, merged: dict[str, Any]) -> dict[str, Any]:
        """Recover a sparse `merged` result with cheaper-first fallback passes.

        Reuses the `sparse_threshold` gate: a dense screen already reads fine
        at full-image scale, so neither fallback pass runs and no extra OCR
        calls are burned. When sparse, tries the fixed-threshold pass FIRST
        (see `_threshold_pass_data`) -- it is cheap (2 `image_to_data` calls,
        vs the tile pass's grid-size many dual-polarity calls) and is exactly
        what recovers a mid-luminance UI block Otsu lumped away. Only if the
        result is STILL sparse after that does the expensive tiled pass run,
        as the last-resort fallback. Fails closed at every step: any error
        running either pass leaves `merged` (or the threshold-enriched
        `merged`) untouched rather than raising.
        """
        word_count = len(data_to_elements(merged, min_confidence=self.min_confidence))
        if word_count >= self.sparse_threshold:
            return merged

        try:
            threshold_data = self._threshold_pass_data(img)
            merged = merge_ocr_passes(merged, threshold_data)
        except Exception:
            pass

        word_count = len(data_to_elements(merged, min_confidence=self.min_confidence))
        if word_count >= self.sparse_threshold:
            return merged

        try:
            tile_data = self._tiled_data(img)
        except Exception:
            return merged
        return merge_ocr_passes(merged, tile_data)

    def detect(self, image_path: Path) -> list[Element]:
        """Run the dual-polarity full-screenshot OCR pass (see `_dual_polarity_data`),
        then the sparse fallback passes -- threshold, then tile (see
        `_maybe_add_sparse_passes`) -- when that pass is sparse."""
        import pytesseract
        from PIL import Image

        image_path = Path(image_path)
        if not image_path.exists():
            return []
        try:
            with Image.open(image_path) as img:
                merged = self._dual_polarity_data(img)
                merged = self._maybe_add_sparse_passes(img, merged)
        except pytesseract.TesseractNotFoundError:
            # The binary disappeared after construction (PATH changed mid-session).
            # A missing OCR binary must never crash perceive — degrade to no OCR.
            return []
        return data_to_elements(merged, min_confidence=self.min_confidence)

    def detect_with_crop(
        self, image_path: Path, window_bounds: tuple[int, int, int, int] | None
    ) -> list[Element]:
        """Like `detect()`, but ADDITIONALLY OCRs a crop of the image at
        `window_bounds` and merges it into the full-screenshot dual-polarity pass.

        Full-page OCR drowns a small text island on a huge screen: proven live
        on a 1920x1200 evidence screenshot where the full-screen pass found
        NONE of a small window's text, while the SAME image cropped to that
        window's bounds read every line verbatim -- tesseract's page
        segmentation is tuned for page-scale layouts, not a 300x200 window on
        a 1920x1200 canvas. Cropping to the already-known active-window bounds
        (padded a few px, clamped to the image) recovers that text; the crop
        pass's `left`/`top` are offset back to full-image/screen coordinates
        before merging with `merge_ocr_passes` so bounds line up with the
        full-screen pass and with UIA elements.

        Fails closed: missing/degenerate `window_bounds`, or any error while
        cropping or OCR-ing the crop, is swallowed and this degrades to the
        plain `detect()` result -- a crop-pass failure must never break perceive.

        The sparse fallback passes (see `_maybe_add_sparse_passes`) also apply
        here, gated on the result AFTER the crop merge: when the active
        window IS the full screen (a fullscreen game/app), the crop pass
        covers the same pixels as the full-image pass and adds nothing, so
        the threshold/tile passes are exactly what recovers a sparse
        fullscreen UI's missed text.
        """
        import pytesseract
        from PIL import Image

        image_path = Path(image_path)
        if not image_path.exists():
            return []
        try:
            with Image.open(image_path) as img:
                merged = self._dual_polarity_data(img)
                crop_box = _resolve_crop_box(img.size, window_bounds)
                if crop_box is not None:
                    try:
                        left, top, _right, _bottom = crop_box
                        data_crop = pytesseract.image_to_data(
                            img.crop(crop_box), output_type=pytesseract.Output.DICT
                        )
                        merged = merge_ocr_passes(merged, _offset_ocr_data(data_crop, left, top))
                    except Exception:
                        pass
                merged = self._maybe_add_sparse_passes(img, merged)
        except pytesseract.TesseractNotFoundError:
            return []
        return data_to_elements(merged, min_confidence=self.min_confidence)


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
