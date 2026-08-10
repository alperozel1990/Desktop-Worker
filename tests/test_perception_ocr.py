"""DW-PERCEPTION-OCR — structured OCR elements + observation enrichment (req §7)."""

import dataclasses
from pathlib import Path

import pytest

from desktop_worker.observation.backends import NullDesktopBackend
from desktop_worker.observation.observer import Observer
from desktop_worker.perception import (
    NullOcrBackend,
    NullUiaBackend,
    Perceiver,
    data_to_elements,
    get_ocr_backend,
)
from desktop_worker.perception.backends import merge_ocr_passes
from desktop_worker.schema.observations import ActiveWindow, Cursor, Element, Observation, Screen


def _perceiver(ocr):
    # Isolate OCR: pin a Null UIA backend so tests don't read the real desktop
    # (uiautomation may be installed on the dev machine).
    return Perceiver(ocr=ocr, uia=NullUiaBackend())


class FakeOcrBackend:
    """Returns a fixed element so the Perceiver can be tested without Tesseract."""

    def __init__(self):
        self.calls = []

    def detect(self, image_path):
        self.calls.append(image_path)
        return [Element(id="ocr-1", type="text", text="Submit",
                        bounds=(10, 20, 80, 40), confidence=0.92, source="ocr")]


def _obs_with_image(tmp_path):
    img = tmp_path / "shot.png"
    img.write_bytes(b"")  # exists with an image suffix; FakeOcr ignores content
    return Observation(screen=Screen(800, 600), cursor=Cursor(0, 0),
                       screenshotRef=str(img))


def _with_active_window(obs, *, bounds):
    return dataclasses.replace(
        obs, activeWindow=ActiveWindow(title="t", process="p", bounds=bounds)
    )


def test_perceiver_enriches_observation_with_elements(tmp_path):
    obs = _obs_with_image(tmp_path)
    enriched = _perceiver(FakeOcrBackend()).perceive(obs)
    assert len(enriched.elements) == 1
    el = enriched.elements[0]
    assert el.text == "Submit"
    assert el.source == "ocr"
    assert el.bounds == (10, 20, 80, 40)
    # serialization carries elements through for the AI / audit
    assert enriched.to_dict()["elements"][0]["text"] == "Submit"


def test_perceiver_skips_non_image_screenshot(tmp_path):
    # Null desktop backend writes a .txt placeholder — OCR must NOT run on it.
    fake = FakeOcrBackend()
    obs = Observer(NullDesktopBackend(), screenshots_dir=tmp_path / "s").observe("t")
    enriched = _perceiver(fake).perceive(obs)
    assert enriched.elements == ()
    assert fake.calls == []          # backend never invoked on a placeholder


def test_null_ocr_backend_returns_empty(tmp_path):
    obs = _obs_with_image(tmp_path)
    enriched = _perceiver(NullOcrBackend()).perceive(obs)
    assert enriched.elements == ()   # graceful: no Tesseract -> no elements, no crash


def test_get_ocr_backend_has_detect(tmp_path):
    backend = get_ocr_backend()
    assert hasattr(backend, "detect")
    assert backend.detect(tmp_path / "missing.png") == []   # degrades, no crash


def test_data_to_elements_robust_to_ragged_and_bad_input():
    assert data_to_elements({}) == []                        # missing keys
    ragged = {"text": ["a", "b"], "conf": ["90"],            # short conf list
              "left": [0], "top": [0], "width": [1], "height": [1]}
    words = [e for e in data_to_elements(ragged) if e.source == "ocr"]
    assert [e.text for e in words] == ["a"]
    bad_conf = {"text": ["x"], "conf": ["n/a"],
                "left": [0], "top": [0], "width": [1], "height": [1]}
    assert data_to_elements(bad_conf) == []                  # non-numeric conf dropped


def test_emitted_element_ids_are_contiguous():
    data = {"text": ["", "A", "", "B"], "conf": ["-1", "90", "-1", "80"],
            "left": [0, 0, 0, 0], "top": [0, 0, 0, 0],
            "width": [1, 1, 1, 1], "height": [1, 1, 1, 1]}
    ids = [e.id for e in data_to_elements(data) if e.source == "ocr"]
    assert ids == ["ocr-0", "ocr-1"]                         # contiguous after filtering


def test_data_to_elements_parses_tesseract_dict():
    data = {
        "text": ["", "Submit", "Cancel", "  "],
        "conf": ["-1", "95", "40", "88"],
        "left": [0, 10, 100, 5],
        "top": [0, 20, 20, 5],
        "width": [0, 70, 60, 0],
        "height": [0, 20, 20, 0],
    }
    elements = [e for e in data_to_elements(data) if e.source == "ocr"]
    # blank texts ("" and "  ") and conf<0 dropped -> Submit + Cancel remain
    assert [e.text for e in elements] == ["Submit", "Cancel"]
    submit = elements[0]
    assert submit.confidence == 0.95
    assert submit.bounds == (10, 20, 80, 40)
    assert submit.source == "ocr"


def test_data_to_elements_min_confidence_filter():
    data = {
        "text": ["low", "high"],
        "conf": ["20", "90"],
        "left": [0, 0], "top": [0, 0], "width": [10, 10], "height": [10, 10],
    }
    elements = [e for e in data_to_elements(data, min_confidence=0.5) if e.source == "ocr"]
    assert [e.text for e in elements] == ["high"]


# --- line-level grouping (block_num, par_num, line_num) --------------------


def test_data_to_elements_groups_multi_word_line():
    # Two words on the same (block, par, line): "New" then "Run", in reading order.
    data = {
        "text": ["New", "Run"],
        "conf": ["90", "80"],
        "left": [10, 60], "top": [20, 22], "width": [40, 30], "height": [15, 18],
        "block_num": [1, 1], "par_num": [1, 1], "line_num": [1, 1],
    }
    lines = [e for e in data_to_elements(data) if e.source == "ocr-line"]
    assert len(lines) == 1
    line = lines[0]
    assert line.id == "ocr-line-0"
    assert line.text == "New Run"                            # space-joined, reading order
    assert line.bounds == (10, 20, 90, 40)                    # union of word bounds
    assert line.confidence == round((0.90 + 0.80) / 2, 3)     # mean of word confidences
    # word elements are untouched alongside the line element
    words = [e for e in data_to_elements(data) if e.source == "ocr"]
    assert [e.text for e in words] == ["New", "Run"]


def test_data_to_elements_single_word_line_still_emits_line_element():
    data = {
        "text": ["Solo"], "conf": ["77"],
        "left": [5], "top": [5], "width": [20], "height": [10],
        "block_num": [1], "par_num": [1], "line_num": [1],
    }
    lines = [e for e in data_to_elements(data) if e.source == "ocr-line"]
    assert len(lines) == 1
    assert lines[0].text == "Solo"
    assert lines[0].bounds == (5, 5, 25, 15)
    assert lines[0].confidence == 0.77


def test_data_to_elements_line_grouping_excludes_low_confidence_words():
    # Same line, but one word is below min_confidence: it must be dropped from
    # BOTH the word list and the line's text/bounds/confidence, consistently.
    data = {
        "text": ["Keep", "Drop", "Also"],
        "conf": ["90", "20", "85"],
        "left": [0, 50, 100], "top": [0, 0, 0], "width": [30, 30, 30], "height": [10, 10, 10],
        "block_num": [2, 2, 2], "par_num": [1, 1, 1], "line_num": [3, 3, 3],
    }
    elements = data_to_elements(data, min_confidence=0.5)
    words = [e for e in elements if e.source == "ocr"]
    lines = [e for e in elements if e.source == "ocr-line"]
    assert [e.text for e in words] == ["Keep", "Also"]        # "Drop" filtered out
    assert len(lines) == 1
    assert lines[0].text == "Keep Also"                       # "Drop" excluded from the join
    assert lines[0].bounds == (0, 0, 130, 10)                 # union excludes Drop's bounds
    assert lines[0].confidence == round((0.90 + 0.85) / 2, 3)


def test_data_to_elements_separates_distinct_lines_and_blocks():
    data = {
        "text": ["Row1Word1", "Row1Word2", "Row2Word1"],
        "conf": ["90", "90", "90"],
        "left": [0, 40, 0], "top": [0, 0, 20], "width": [30, 30, 30], "height": [10, 10, 10],
        "block_num": [1, 1, 1], "par_num": [1, 1, 1], "line_num": [1, 1, 2],
    }
    lines = [e for e in data_to_elements(data) if e.source == "ocr-line"]
    assert [e.text for e in lines] == ["Row1Word1 Row1Word2", "Row2Word1"]


def test_data_to_elements_empty_dict_is_safe():
    assert data_to_elements({}) == []


# --- dual-polarity OCR merge (UQC-OCR-dualpol) ------------------------------
#
# Tesseract binarizes per image, not per region: a small light-on-dark (or
# dark-on-light) island inside a screen that is mostly the opposite polarity
# is often read as noise and dropped entirely -- proven live on a light
# tkinter window sitting on a dark terminal: zero words came back from
# inside the clearly-legible window. TesseractOcrBackend.detect now runs a
# second OCR pass on an inverted copy and merges it in via merge_ocr_passes.


def test_merge_ocr_passes_keeps_both_polarities_words_exactly_once():
    data_normal = {
        "text": ["TerminalWord"], "conf": ["90"],
        "left": [0], "top": [0], "width": [80], "height": [20],
        "block_num": [1], "par_num": [1], "line_num": [1],
    }
    data_inverted = {
        "text": ["WindowWord"], "conf": ["88"],
        "left": [200], "top": [200], "width": [80], "height": [20],
        "block_num": [1], "par_num": [1], "line_num": [1],
    }
    merged = merge_ocr_passes(data_normal, data_inverted)
    words = [e for e in data_to_elements(merged) if e.source == "ocr"]
    assert sorted(e.text for e in words) == ["TerminalWord", "WindowWord"]
    assert len(words) == 2  # each polarity's word survives exactly once


def test_merge_ocr_passes_dedupes_overlapping_same_text_keeps_higher_confidence():
    data_normal = {
        "text": ["Submit"], "conf": ["40"],  # low-confidence normal-pass read
        "left": [10], "top": [10], "width": [60], "height": [20],
        "block_num": [1], "par_num": [1], "line_num": [1],
    }
    data_inverted = {
        "text": ["submit"], "conf": ["93"],  # same word/spot, case differs, higher conf
        "left": [11], "top": [10], "width": [60], "height": [20],
        "block_num": [1], "par_num": [1], "line_num": [1],
    }
    merged = merge_ocr_passes(data_normal, data_inverted)
    words = [e for e in data_to_elements(merged) if e.source == "ocr"]
    assert len(words) == 1  # duplicate collapsed, not two entries
    assert words[0].text.lower() == "submit"
    assert words[0].confidence == 0.93  # the higher-confidence side wins


def test_merge_ocr_passes_non_overlapping_same_text_are_not_deduped():
    # Same word text appearing twice on screen at different locations must
    # NOT be collapsed into one -- dedupe is text AND spatial overlap.
    data_normal = {
        "text": ["OK"], "conf": ["90"],
        "left": [0], "top": [0], "width": [20], "height": [10],
        "block_num": [1], "par_num": [1], "line_num": [1],
    }
    data_inverted = {
        "text": ["OK"], "conf": ["85"],
        "left": [500], "top": [500], "width": [20], "height": [10],
        "block_num": [1], "par_num": [1], "line_num": [1],
    }
    merged = merge_ocr_passes(data_normal, data_inverted)
    words = [e for e in data_to_elements(merged) if e.source == "ocr"]
    assert len(words) == 2


def test_merge_ocr_passes_one_empty_pass_leaves_the_other_unchanged():
    data_normal = {
        "text": ["New", "Run"], "conf": ["90", "80"],
        "left": [10, 60], "top": [20, 22], "width": [40, 30], "height": [15, 18],
        "block_num": [1, 1], "par_num": [1, 1], "line_num": [1, 1],
    }
    baseline = data_to_elements(data_normal)

    merged_vs_empty_dict = merge_ocr_passes(data_normal, {})
    assert data_to_elements(merged_vs_empty_dict) == baseline

    empty_words = {"text": [], "conf": [], "left": [], "top": [], "width": [], "height": []}
    merged_vs_empty_words = merge_ocr_passes(data_normal, empty_words)
    assert data_to_elements(merged_vs_empty_words) == baseline

    # symmetric: normal pass empty, inverted pass carries the words
    merged_reversed = merge_ocr_passes({}, data_normal)
    assert data_to_elements(merged_reversed) == baseline


def test_merge_ocr_passes_offsets_block_num_to_avoid_cross_pass_line_fusion():
    # Both passes independently report (block=1, par=1, line=1); without an
    # offset the two unrelated lines would wrongly fuse into one line element.
    data_normal = {
        "text": ["Alpha"], "conf": ["90"],
        "left": [0], "top": [0], "width": [40], "height": [10],
        "block_num": [1], "par_num": [1], "line_num": [1],
    }
    data_inverted = {
        "text": ["Beta"], "conf": ["90"],
        "left": [500], "top": [500], "width": [40], "height": [10],
        "block_num": [1], "par_num": [1], "line_num": [1],
    }
    merged = merge_ocr_passes(data_normal, data_inverted)
    lines = [e for e in data_to_elements(merged) if e.source == "ocr-line"]
    assert sorted(e.text for e in lines) == ["Alpha", "Beta"]  # two distinct lines, not fused


def _solid_image_path(tmp_path, color):
    from PIL import Image

    img = tmp_path / f"shot_{'-'.join(str(c) for c in color)}.png"
    Image.new("RGB", (40, 40), color).save(img)
    return img


def test_detect_merges_normal_and_inverted_polarity_passes(tmp_path, monkeypatch):
    pytest.importorskip("pytesseract")
    pytest.importorskip("PIL")
    import pytesseract

    from desktop_worker.perception.backends import TesseractOcrBackend

    monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda *a, **k: "5.4.0")
    # sparse_threshold=0 disables the tiled pass (tested separately below) so
    # this test's polarity-only fake isn't also asked to answer for tile crops.
    backend = TesseractOcrBackend(sparse_threshold=0)

    data_normal_polarity = {
        "text": ["TerminalWord"], "conf": ["90"],
        "left": [0], "top": [0], "width": [80], "height": [20],
        "block_num": [1], "par_num": [1], "line_num": [1],
    }
    data_inverted_polarity = {
        "text": ["WindowWord"], "conf": ["88"],
        "left": [5], "top": [5], "width": [30], "height": [10],
        "block_num": [1], "par_num": [1], "line_num": [1],
    }

    def fake_image_to_data(img, output_type=None):
        # detect() calls image_to_data once on the original image and once on
        # ImageOps.invert(img.convert("RGB")) -- distinguish passes by pixel color,
        # exactly like a real light-window-on-dark-terminal screenshot would differ.
        pixel = img.convert("RGB").getpixel((0, 0))
        return data_normal_polarity if pixel == (255, 255, 255) else data_inverted_polarity

    monkeypatch.setattr(pytesseract, "image_to_data", fake_image_to_data)

    img_path = _solid_image_path(tmp_path, (255, 255, 255))
    elements = backend.detect(img_path)
    words = [e for e in elements if e.source == "ocr"]
    assert sorted(e.text for e in words) == ["TerminalWord", "WindowWord"]


def test_detect_single_polarity_behavior_is_unchanged(tmp_path, monkeypatch):
    pytest.importorskip("pytesseract")
    pytest.importorskip("PIL")
    import pytesseract

    from desktop_worker.perception.backends import TesseractOcrBackend

    monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda *a, **k: "5.4.0")
    # sparse_threshold=0 disables the tiled pass (tested separately below) so
    # this test's polarity-only fake isn't also asked to answer for tile crops.
    backend = TesseractOcrBackend(sparse_threshold=0)

    data_normal_polarity = {
        "text": ["Only"], "conf": ["77"],
        "left": [1], "top": [1], "width": [30], "height": [10],
        "block_num": [1], "par_num": [1], "line_num": [1],
    }

    def fake_image_to_data(img, output_type=None):
        pixel = img.convert("RGB").getpixel((0, 0))
        return data_normal_polarity if pixel == (255, 255, 255) else {}

    monkeypatch.setattr(pytesseract, "image_to_data", fake_image_to_data)

    img_path = _solid_image_path(tmp_path, (255, 255, 255))
    elements = backend.detect(img_path)
    words = [e for e in elements if e.source == "ocr"]
    assert [e.text for e in words] == ["Only"]
    assert words[0].confidence == 0.77
    assert words[0].bounds == (1, 1, 31, 11)


# --- active-window crop OCR pass (UQC-OCR-cropwin) --------------------------
#
# Tesseract's page segmentation is tuned for page-scale layouts, not a small
# window on a huge screen: proven live on a 1920x1200 evidence screenshot
# where the full-screen pass found NONE of a small window's text, while the
# SAME image cropped to that window's bounds read every line verbatim.
# TesseractOcrBackend.detect_with_crop ADDITIONALLY OCRs a crop of the known
# activeWindow bounds and merges it into the full-screen dual-polarity pass.


def test_detect_with_crop_merges_full_and_crop_passes_with_screen_offset(tmp_path, monkeypatch):
    pytest.importorskip("pytesseract")
    pytest.importorskip("PIL")
    import pytesseract

    from desktop_worker.perception.backends import TesseractOcrBackend

    monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda *a, **k: "5.4.0")
    # sparse_threshold=0 disables the tiled pass (tested separately below) so
    # this test's size-keyed fake isn't also asked to answer for tile crops.
    backend = TesseractOcrBackend(sparse_threshold=0)

    full_data = {
        "text": ["FullScreenWord"], "conf": ["90"],
        "left": [5], "top": [5], "width": [40], "height": [10],
        "block_num": [1], "par_num": [1], "line_num": [1],
    }
    # Coordinates here are RELATIVE TO THE CROP -- the word sits 3px from the
    # crop's own top-left, which is itself offset from the full image.
    crop_data = {
        "text": ["SmallWindowWord"], "conf": ["85"],
        "left": [3], "top": [3], "width": [50], "height": [12],
        "block_num": [1], "par_num": [1], "line_num": [1],
    }

    def fake_image_to_data(img, output_type=None):
        # The full-screen passes (normal + inverted) run on the 200x200
        # image; the crop pass runs on the smaller cropped region.
        if img.size == (200, 200):
            return full_data
        return crop_data

    monkeypatch.setattr(pytesseract, "image_to_data", fake_image_to_data)

    from PIL import Image

    img_path = tmp_path / "shot.png"
    Image.new("RGB", (200, 200), (255, 255, 255)).save(img_path)

    # Window bounds in screen/image coordinates; padded (8px) + clamped crop
    # box starts at (100-8, 100-8) = (92, 92).
    elements = backend.detect_with_crop(img_path, window_bounds=(100, 100, 150, 130))
    words = {e.text: e for e in elements if e.source == "ocr"}

    assert "FullScreenWord" in words
    assert "SmallWindowWord" in words
    # Crop-pass bounds are offset back to full-image/screen coordinates:
    # crop origin (92, 92) + local (3, 3) = (95, 95).
    crop_word = words["SmallWindowWord"]
    assert crop_word.bounds == (95, 95, 145, 107)


def test_detect_with_crop_skips_degenerate_bounds_fail_closed(tmp_path, monkeypatch):
    pytest.importorskip("pytesseract")
    pytest.importorskip("PIL")
    import pytesseract

    from desktop_worker.perception.backends import TesseractOcrBackend

    monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda *a, **k: "5.4.0")
    # sparse_threshold=0 disables the tiled pass (tested separately below) so
    # `calls` only reflects the full-screen + crop passes this test targets.
    backend = TesseractOcrBackend(sparse_threshold=0)

    full_data = {
        "text": ["FullScreenWord"], "conf": ["90"],
        "left": [5], "top": [5], "width": [40], "height": [10],
        "block_num": [1], "par_num": [1], "line_num": [1],
    }
    calls = []

    def fake_image_to_data(img, output_type=None):
        calls.append(img.size)
        return full_data

    monkeypatch.setattr(pytesseract, "image_to_data", fake_image_to_data)

    from PIL import Image

    img_path = tmp_path / "shot.png"
    Image.new("RGB", (200, 200), (255, 255, 255)).save(img_path)

    # Zero-area bounds (right == left, bottom == top) are degenerate -> skip.
    elements = backend.detect_with_crop(img_path, window_bounds=(100, 100, 100, 100))
    words = [e.text for e in elements if e.source == "ocr"]
    assert words == ["FullScreenWord"]
    # Only the two full-screen passes ran (normal + inverted) -- no crop call.
    assert len(calls) == 2

    calls.clear()
    # Missing bounds must also fail closed, never raise.
    elements = backend.detect_with_crop(img_path, window_bounds=None)
    words = [e.text for e in elements if e.source == "ocr"]
    assert words == ["FullScreenWord"]
    assert len(calls) == 2


class FakeCropOcrBackend:
    """OCR backend exposing the additive `detect_with_crop` capability."""

    def __init__(self):
        self.detect_calls = []
        self.crop_calls = []

    def detect(self, image_path):
        self.detect_calls.append(image_path)
        return [Element(id="ocr-full", type="text", text="FullOnly",
                        bounds=(0, 0, 50, 20), confidence=0.9, source="ocr")]

    def detect_with_crop(self, image_path, window_bounds):
        self.crop_calls.append((image_path, window_bounds))
        return [
            Element(id="ocr-full", type="text", text="FullOnly",
                    bounds=(0, 0, 50, 20), confidence=0.9, source="ocr"),
            Element(id="ocr-crop", type="text", text="CroppedOnly",
                    bounds=(130, 130, 180, 150), confidence=0.8, source="ocr"),
        ]


def test_perceiver_uses_crop_pass_when_active_window_bounds_present(tmp_path):
    backend = FakeCropOcrBackend()
    obs = _obs_with_image(tmp_path)
    obs = _with_active_window(obs, bounds=(100, 100, 200, 150))

    enriched = _perceiver(backend).perceive(obs)

    texts = {e.text for e in enriched.elements}
    assert "FullOnly" in texts
    assert "CroppedOnly" in texts
    assert backend.crop_calls == [(Path(obs.screenshotRef), (100, 100, 200, 150))]
    assert backend.detect_calls == []  # crop-capable backend takes the crop path


def test_perceiver_falls_back_to_plain_detect_without_active_window(tmp_path):
    backend = FakeCropOcrBackend()
    obs = _obs_with_image(tmp_path)  # no activeWindow -> no bounds to crop with

    enriched = _perceiver(backend).perceive(obs)

    assert backend.detect_calls
    assert backend.crop_calls == []
    assert {e.text for e in enriched.elements} == {"FullOnly"}


def test_perceiver_backward_compatible_with_backend_lacking_crop_support(tmp_path):
    # A backend implementing ONLY detect() (the pre-existing protocol) must keep
    # working unchanged even when activeWindow bounds ARE present.
    backend = FakeOcrBackend()
    obs = _obs_with_image(tmp_path)
    obs = _with_active_window(obs, bounds=(10, 10, 50, 50))

    enriched = _perceiver(backend).perceive(obs)

    assert enriched.elements[0].text == "Submit"
    assert backend.calls  # plain detect still invoked, no AttributeError


# --- tiled OCR pass for sparse fullscreen UIs (UQC-OCR-tiles) ---------------
#
# Proven live on the DiceNDecks home screen (1920x1200, mostly dark): the
# full-screen pass AND the active-window crop pass (identical to full-screen,
# since the window IS the screen) both missed two large, clearly-legible
# buttons. Tesseract's page segmentation assumes page-scale layouts and
# under-segments a screen that is mostly flat color with a few small text
# islands. TesseractOcrBackend now runs a GENERIC overlapping tile grid pass
# -- reusing the existing dual-polarity-per-tile primitive -- gated behind a
# sparse_threshold so dense screens (which already read fine) skip the extra
# cost.


def test_tile_boxes_covers_image_with_overlapping_seams():
    from desktop_worker.perception.backends import _tile_boxes

    boxes = _tile_boxes((300, 200), grid=(3, 2), overlap=0.1)
    assert len(boxes) == 6
    assert min(b[0] for b in boxes) == 0
    assert max(b[2] for b in boxes) == 300
    assert min(b[1] for b in boxes) == 0
    assert max(b[3] for b in boxes) == 200
    # adjacent tiles in row 0 share a strip of pixels (right edge of the left
    # tile lands past the left edge of its neighbour) -- proves the overlap.
    row0 = sorted((b for b in boxes if b[1] == 0), key=lambda b: b[0])
    assert row0[0][2] > row0[1][0]


def test_tile_boxes_degenerate_image_size_returns_no_tiles():
    from desktop_worker.perception.backends import _tile_boxes

    assert _tile_boxes((0, 200), grid=(3, 2), overlap=0.1) == []
    assert _tile_boxes((300, 0), grid=(3, 2), overlap=0.1) == []


def test_tesseract_backend_default_sparse_threshold_is_20(monkeypatch):
    pytest.importorskip("pytesseract")
    pytest.importorskip("PIL")
    import pytesseract

    from desktop_worker.perception.backends import (
        DEFAULT_SPARSE_THRESHOLD,
        TesseractOcrBackend,
    )

    monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda *a, **k: "5.4.0")
    backend = TesseractOcrBackend()
    assert DEFAULT_SPARSE_THRESHOLD == 20
    assert backend.sparse_threshold == 20


def test_tesseract_tiled_pass_offsets_tile_words_to_screen_coordinates(tmp_path, monkeypatch):
    pytest.importorskip("pytesseract")
    pytest.importorskip("PIL")
    import pytesseract

    from desktop_worker.perception.backends import TesseractOcrBackend, _tile_boxes

    monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda *a, **k: "5.4.0")
    # sparse_threshold=5 so a fake full-image pass returning 0 words is sparse.
    backend = TesseractOcrBackend(sparse_threshold=5, tile_grid=(3, 2), tile_overlap=0.1)

    from PIL import Image

    img_path = tmp_path / "shot.png"
    Image.new("RGB", (303, 204), (255, 255, 255)).save(img_path)

    boxes = _tile_boxes((303, 204), grid=(3, 2), overlap=0.1)
    sizes = [(b[2] - b[0], b[3] - b[1]) for b in boxes]
    target_box = boxes[4]
    target_size = sizes[4]
    assert sizes.count(target_size) == 1  # size alone identifies this tile

    empty = {"text": [], "conf": [], "left": [], "top": [], "width": [], "height": []}

    def fake_dual_polarity(img):
        # Reuses (and proves reuse of) the existing dual-polarity primitive:
        # detect() calls it once for the full image, then once per tile crop.
        if img.size == target_size:
            return {
                "text": ["TileWord"], "conf": ["91"],
                "left": [4], "top": [6], "width": [50], "height": [15],
                "block_num": [1], "par_num": [1], "line_num": [1],
            }
        return empty

    monkeypatch.setattr(TesseractOcrBackend, "_dual_polarity_data", staticmethod(fake_dual_polarity))

    elements = backend.detect(img_path)
    words = {e.text: e for e in elements if e.source == "ocr"}
    assert "TileWord" in words
    left, top = target_box[0], target_box[1]
    # the tile-local (4, 6) offset by the tile's own screen-space origin.
    assert words["TileWord"].bounds == (left + 4, top + 6, left + 4 + 50, top + 6 + 15)


def test_tesseract_tiled_pass_dedupes_word_seen_in_two_overlapping_tiles(tmp_path, monkeypatch):
    pytest.importorskip("pytesseract")
    pytest.importorskip("PIL")
    import pytesseract

    from desktop_worker.perception.backends import TesseractOcrBackend, _tile_boxes

    monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda *a, **k: "5.4.0")
    backend = TesseractOcrBackend(sparse_threshold=5, tile_grid=(3, 2), tile_overlap=0.1)

    from PIL import Image

    img_path = tmp_path / "shot.png"
    Image.new("RGB", (303, 204), (255, 255, 255)).save(img_path)

    boxes = _tile_boxes((303, 204), grid=(3, 2), overlap=0.1)
    box_a, box_b = boxes[0], boxes[1]  # adjacent tiles in row 0 -- their seam overlaps
    size_a = (box_a[2] - box_a[0], box_a[3] - box_a[1])
    size_b = (box_b[2] - box_b[0], box_b[3] - box_b[1])
    assert size_a != size_b  # distinguishable by size in the fake below

    overlap_left, overlap_right = box_b[0], box_a[2]
    assert overlap_right - overlap_left >= 18  # word fits inside the shared strip
    word_left, word_top, word_w, word_h = overlap_left + 2, box_a[1] + 5, 15, 8

    empty = {"text": [], "conf": [], "left": [], "top": [], "width": [], "height": []}

    def fake_dual_polarity(img):
        if img.size == size_a:
            local_left, local_top = word_left - box_a[0], word_top - box_a[1]
            return {
                "text": ["OverlapWord"], "conf": ["80"],  # lower-confidence read
                "left": [local_left], "top": [local_top], "width": [word_w], "height": [word_h],
                "block_num": [1], "par_num": [1], "line_num": [1],
            }
        if img.size == size_b:
            local_left, local_top = word_left - box_b[0], word_top - box_b[1]
            return {
                "text": ["OverlapWord"], "conf": ["95"],  # higher-confidence read, same word
                "left": [local_left], "top": [local_top], "width": [word_w], "height": [word_h],
                "block_num": [1], "par_num": [1], "line_num": [1],
            }
        return empty

    monkeypatch.setattr(TesseractOcrBackend, "_dual_polarity_data", staticmethod(fake_dual_polarity))

    elements = backend.detect(img_path)
    words = [e for e in elements if e.source == "ocr" and e.text == "OverlapWord"]
    assert len(words) == 1  # the two tiles' reads of the same word collapse to one
    assert words[0].confidence == 0.95  # higher-confidence tile's read wins
    assert words[0].bounds == (word_left, word_top, word_left + word_w, word_top + word_h)


def test_tesseract_tiled_pass_skipped_when_full_pass_is_dense(tmp_path, monkeypatch):
    pytest.importorskip("pytesseract")
    pytest.importorskip("PIL")
    import pytesseract

    from desktop_worker.perception.backends import TesseractOcrBackend

    monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda *a, **k: "5.4.0")
    backend = TesseractOcrBackend(sparse_threshold=3, tile_grid=(3, 2), tile_overlap=0.1)

    from PIL import Image

    img_path = tmp_path / "shot.png"
    Image.new("RGB", (303, 204), (255, 255, 255)).save(img_path)

    calls = []
    dense_data = {
        "text": ["One", "Two", "Three"], "conf": ["90", "90", "90"],
        "left": [0, 40, 80], "top": [0, 0, 0], "width": [30, 30, 30], "height": [10, 10, 10],
        "block_num": [1, 1, 1], "par_num": [1, 1, 1], "line_num": [1, 1, 1],
    }

    def fake_dual_polarity(img):
        calls.append(img.size)
        return dense_data

    monkeypatch.setattr(TesseractOcrBackend, "_dual_polarity_data", staticmethod(fake_dual_polarity))

    elements = backend.detect(img_path)
    words = [e for e in elements if e.source == "ocr"]
    assert len(words) == 3  # 3 words >= sparse_threshold=3 -> dense, tiling skipped
    assert calls == [(303, 204)]  # only the single full-image call ran, no tile crops


def test_tesseract_tiled_pass_runs_on_crop_path_when_crop_merge_is_still_sparse(tmp_path, monkeypatch):
    # The live failure this closes: a fullscreen game's active window IS the
    # full screen, so detect_with_crop's crop pass covers identical pixels
    # and adds nothing -- the tiled pass must still fire off the sparse
    # full+crop merge to recover the missed text.
    pytest.importorskip("pytesseract")
    pytest.importorskip("PIL")
    import pytesseract

    from desktop_worker.perception.backends import TesseractOcrBackend, _tile_boxes

    monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda *a, **k: "5.4.0")
    backend = TesseractOcrBackend(sparse_threshold=5, tile_grid=(3, 2), tile_overlap=0.1)

    from PIL import Image

    img_path = tmp_path / "shot.png"
    Image.new("RGB", (303, 204), (255, 255, 255)).save(img_path)

    boxes = _tile_boxes((303, 204), grid=(3, 2), overlap=0.1)
    target_box = boxes[3]
    target_size = (target_box[2] - target_box[0], target_box[3] - target_box[1])
    empty = {"text": [], "conf": [], "left": [], "top": [], "width": [], "height": []}

    def fake_dual_polarity(img):
        if img.size == target_size:
            return {
                "text": ["TileOnly"], "conf": ["90"],
                "left": [2], "top": [2], "width": [40], "height": [12],
                "block_num": [1], "par_num": [1], "line_num": [1],
            }
        return empty

    monkeypatch.setattr(TesseractOcrBackend, "_dual_polarity_data", staticmethod(fake_dual_polarity))
    # window_bounds == the whole image, like a fullscreen app's active window;
    # image_to_data is only used for the (identical-to-full) crop pass here.
    monkeypatch.setattr(pytesseract, "image_to_data", lambda img, output_type=None: dict(empty))

    elements = backend.detect_with_crop(img_path, window_bounds=(0, 0, 303, 204))
    words = [e.text for e in elements if e.source == "ocr"]
    assert "TileOnly" in words
