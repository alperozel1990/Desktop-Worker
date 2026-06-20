"""DW-PERCEPTION-OCR — structured OCR elements + observation enrichment (req §7)."""

from desktop_worker.observation.backends import NullDesktopBackend
from desktop_worker.observation.observer import Observer
from desktop_worker.perception import (
    NullOcrBackend,
    Perceiver,
    data_to_elements,
    get_ocr_backend,
)
from desktop_worker.schema.observations import Cursor, Element, Observation, Screen


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


def test_perceiver_enriches_observation_with_elements(tmp_path):
    obs = _obs_with_image(tmp_path)
    enriched = Perceiver(FakeOcrBackend()).perceive(obs)
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
    enriched = Perceiver(fake).perceive(obs)
    assert enriched.elements == ()
    assert fake.calls == []          # backend never invoked on a placeholder


def test_null_ocr_backend_returns_empty(tmp_path):
    obs = _obs_with_image(tmp_path)
    enriched = Perceiver(NullOcrBackend()).perceive(obs)
    assert enriched.elements == ()   # graceful: no Tesseract -> no elements, no crash


def test_get_ocr_backend_has_detect(tmp_path):
    backend = get_ocr_backend()
    assert hasattr(backend, "detect")
    assert backend.detect(tmp_path / "missing.png") == []   # degrades, no crash


def test_data_to_elements_robust_to_ragged_and_bad_input():
    assert data_to_elements({}) == []                        # missing keys
    ragged = {"text": ["a", "b"], "conf": ["90"],            # short conf list
              "left": [0], "top": [0], "width": [1], "height": [1]}
    assert [e.text for e in data_to_elements(ragged)] == ["a"]
    bad_conf = {"text": ["x"], "conf": ["n/a"],
                "left": [0], "top": [0], "width": [1], "height": [1]}
    assert data_to_elements(bad_conf) == []                  # non-numeric conf dropped


def test_emitted_element_ids_are_contiguous():
    data = {"text": ["", "A", "", "B"], "conf": ["-1", "90", "-1", "80"],
            "left": [0, 0, 0, 0], "top": [0, 0, 0, 0],
            "width": [1, 1, 1, 1], "height": [1, 1, 1, 1]}
    ids = [e.id for e in data_to_elements(data)]
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
    elements = data_to_elements(data)
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
    elements = data_to_elements(data, min_confidence=0.5)
    assert [e.text for e in elements] == ["high"]
