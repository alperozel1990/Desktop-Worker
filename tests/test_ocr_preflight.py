"""Tests for the OCR preflight / health check (DW-OCR-PREFLIGHT).

The whole point of this feature is that a missing OCR stack does NOT fail loudly —
it just makes perception quietly thinner, and on an OCR-heavy app (KiCad reads 46
elements without OCR vs 193 with it) a 4x undercount looks like a healthy result.
So these tests pin that the health is REPORTED, honestly, in every direction.
"""

import builtins

import pytest

from desktop_worker.perception import ocr_status


def test_ocr_status_has_a_stable_shape():
    s = ocr_status()
    assert set(s) == {"available", "backend", "version", "missing", "reason"}
    assert isinstance(s["missing"], list)
    assert s["backend"] in ("tesseract", "null")
    # available and backend must agree — a green light with a null backend would be
    # exactly the silent-undercount lie this feature exists to prevent.
    assert (s["backend"] == "tesseract") == s["available"]


def _hide(monkeypatch, *modules):
    real_import = builtins.__import__

    def fake(name, *a, **k):
        if name in modules or name.split(".")[0] in modules:
            raise ImportError(f"hidden for test: {name}")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)


def test_missing_pytesseract_is_reported_as_unavailable(monkeypatch):
    _hide(monkeypatch, "pytesseract")
    s = ocr_status()
    assert s["available"] is False
    assert "pytesseract" in s["missing"]
    assert s["backend"] == "null"


def test_missing_pillow_is_reported(monkeypatch):
    _hide(monkeypatch, "PIL")
    s = ocr_status()
    assert s["available"] is False
    assert "Pillow" in s["missing"]


def test_binding_present_but_binary_absent_is_the_named_common_case(monkeypatch):
    """pytesseract imports, but the tesseract EXE is not on PATH — the state the
    installer commonly leaves, and the one that most looks 'fine' but is not."""
    import pytesseract

    def boom():
        raise EnvironmentError("tesseract is not installed or it's not in your PATH")

    monkeypatch.setattr(pytesseract, "get_tesseract_version", boom)
    s = ocr_status()
    assert s["available"] is False
    assert s["missing"] == ["tesseract-binary"]
    assert "PATH" in s["reason"]


def test_when_everything_is_present_it_reports_ready(monkeypatch):
    pytest.importorskip("pytesseract")
    pytest.importorskip("PIL")
    import pytesseract

    monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "5.4.0")
    s = ocr_status()
    assert s["available"] is True
    assert s["version"] == "5.4.0"
    assert s["missing"] == []
    assert "ready" in s["reason"].lower()


# --- regression: a missing binary must degrade, never crash perceive --------


def test_factory_falls_back_to_null_when_binary_is_absent(monkeypatch):
    """Found live: pytesseract present + binary absent constructed a real backend
    whose first detect() raised TesseractNotFoundError and crashed perceive. The
    constructor now probes the binary so the factory falls back to Null instead."""
    pytest.importorskip("pytesseract")
    import pytesseract

    from desktop_worker.perception.backends import NullOcrBackend, get_ocr_backend

    monkeypatch.setattr(
        pytesseract, "get_tesseract_version",
        lambda *a, **k: (_ for _ in ()).throw(pytesseract.TesseractNotFoundError()),
    )
    assert isinstance(get_ocr_backend(True), NullOcrBackend)


def test_detect_returns_empty_when_binary_vanishes_mid_session(tmp_path, monkeypatch):
    """PATH can change after construction; detect must degrade, not raise."""
    pytest.importorskip("pytesseract")
    pytest.importorskip("PIL")
    import pytesseract

    from desktop_worker.perception.backends import TesseractOcrBackend

    # Construct while the binary "exists"...
    monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda *a, **k: "5.4.0")
    backend = TesseractOcrBackend()

    # ...then it disappears before detect().
    img = tmp_path / "shot.png"
    from PIL import Image
    Image.new("RGB", (4, 4), "white").save(img)

    def boom(*a, **k):
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(pytesseract, "image_to_data", boom)
    assert backend.detect(img) == []  # degraded, not crashed
