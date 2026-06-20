"""DW-PERCEPTION-UIA — UIA elements + UIA-preferred merge (requirements §7)."""

from desktop_worker.perception import (
    NullUiaBackend,
    Perceiver,
    control_to_type,
    get_uia_backend,
    merge_elements,
)
from desktop_worker.schema.observations import Cursor, Element, Observation, Screen


def _el(id, source, bounds, type="button", text=None):
    return Element(id=id, type=type, bounds=bounds, source=source, text=text)


def test_control_type_mapping():
    assert control_to_type("ButtonControl") == "button"
    assert control_to_type("Edit") == "input"
    assert control_to_type("CheckBoxControl") == "checkbox"
    assert control_to_type("HyperlinkControl") == "link"
    assert control_to_type("SomethingWeird") == "unknown"


def test_merge_prefers_uia_and_drops_overlapping_ocr():
    uia = [_el("uia-0", "uia", (0, 0, 100, 50), text="Submit")]
    # ocr-a center (50,25) is INSIDE the uia bounds -> dropped as duplicate.
    ocr_inside = _el("ocr-0", "ocr", (10, 10, 90, 40), type="text", text="Submit")
    # ocr-b center (250,25) is OUTSIDE -> kept (fills a gap UIA missed).
    ocr_outside = _el("ocr-1", "ocr", (200, 10, 300, 40), type="text", text="Other")
    merged = merge_elements(uia, [ocr_inside, ocr_outside])
    sources = [(e.source, e.text) for e in merged]
    assert ("uia", "Submit") in sources
    assert ("ocr", "Other") in sources
    assert ("ocr", "Submit") not in sources       # overlapping OCR dropped
    assert len(merged) == 2


def test_merge_keeps_all_uia():
    uia = [_el("uia-0", "uia", (0, 0, 10, 10)), _el("uia-1", "uia", (20, 20, 30, 30))]
    assert len(merge_elements(uia, [])) == 2


def test_perceiver_merges_uia_then_ocr(tmp_path):
    img = tmp_path / "shot.png"
    img.write_bytes(b"")

    class FakeUia:
        def detect(self):
            return [_el("uia-0", "uia", (0, 0, 100, 50), text="OK")]

    class FakeOcr:
        def detect(self, path):
            return [_el("ocr-0", "ocr", (200, 0, 260, 20), type="text", text="far")]

    obs = Observation(screen=Screen(800, 600), cursor=Cursor(0, 0), screenshotRef=str(img))
    enriched = Perceiver(ocr=FakeOcr(), uia=FakeUia()).perceive(obs)
    by_source = {e.source for e in enriched.elements}
    assert by_source == {"uia", "ocr"}
    assert enriched.to_dict()["elements"][0]["source"] == "uia"   # UIA listed first


def test_perceiver_uia_only_without_screenshot():
    class FakeUia:
        def detect(self):
            return [_el("uia-0", "uia", (0, 0, 10, 10), text="x")]

    obs = Observation(screen=Screen(800, 600), cursor=Cursor(0, 0), screenshotRef=None)
    enriched = Perceiver(uia=FakeUia()).perceive(obs)
    assert len(enriched.elements) == 1
    assert enriched.elements[0].source == "uia"


def test_null_uia_backend_and_factory():
    assert NullUiaBackend().detect() == []
    assert hasattr(get_uia_backend(), "detect")     # always returns a usable backend
