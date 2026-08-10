"""Tests for the OCR preflight / health check (DW-OCR-PREFLIGHT).

The whole point of this feature is that a missing OCR stack does NOT fail loudly —
it just makes perception quietly thinner, and on an OCR-heavy app (KiCad reads 46
elements without OCR vs 193 with it) a 4x undercount looks like a healthy result.
So these tests pin that the health is REPORTED, honestly, in every direction.
"""

import builtins
import shutil

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


# --- regression: resolve the binary without relying on inherited PATH -------
#
# A child process spawned with a minimal/sanitized environment (e.g. the MCP
# server under a headless launcher) may have NO PATH at all, so
# pytesseract.get_tesseract_version() -- which shells out to a bare
# "tesseract" -- fails even though the binary is installed. These tests pin
# the resolution precedence: TESSERACT_CMD env var > shutil.which > well-known
# install dirs > None (fail closed).


def _clear_tesseract_env(monkeypatch):
    for var in ("TESSERACT_CMD", "ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        monkeypatch.delenv(var, raising=False)


def test_resolve_tesseract_cmd_env_var_wins(monkeypatch):
    from desktop_worker.perception.backends import resolve_tesseract_cmd

    _clear_tesseract_env(monkeypatch)
    monkeypatch.setenv("TESSERACT_CMD", r"C:\custom\tesseract.exe")
    # even if PATH would resolve something else, the explicit override wins
    monkeypatch.setattr(shutil, "which", lambda name: r"C:\path\tesseract.exe")
    assert resolve_tesseract_cmd() == r"C:\custom\tesseract.exe"


def test_resolve_tesseract_cmd_falls_back_to_which(monkeypatch):
    from desktop_worker.perception.backends import resolve_tesseract_cmd

    _clear_tesseract_env(monkeypatch)
    monkeypatch.setattr(shutil, "which", lambda name: r"C:\path\tesseract.exe")
    assert resolve_tesseract_cmd() == r"C:\path\tesseract.exe"


def test_resolve_tesseract_cmd_falls_back_to_well_known_dir(tmp_path, monkeypatch):
    from desktop_worker.perception.backends import resolve_tesseract_cmd

    _clear_tesseract_env(monkeypatch)
    monkeypatch.setattr(shutil, "which", lambda name: None)  # not on PATH
    program_files = tmp_path / "Program Files"
    tesseract_dir = program_files / "Tesseract-OCR"
    tesseract_dir.mkdir(parents=True)
    exe = tesseract_dir / "tesseract.exe"
    exe.write_bytes(b"")
    monkeypatch.setenv("ProgramFiles", str(program_files))
    assert resolve_tesseract_cmd() == str(exe)


def test_resolve_tesseract_cmd_returns_none_when_nothing_found(tmp_path, monkeypatch):
    from desktop_worker.perception.backends import resolve_tesseract_cmd

    _clear_tesseract_env(monkeypatch)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    # well-known dirs point at real env vars but the exe is absent there
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "nope"))
    assert resolve_tesseract_cmd() is None


def test_construction_sets_tesseract_cmd_from_resolution(monkeypatch):
    """The constructor must set pytesseract.pytesseract.tesseract_cmd from the
    resolved path BEFORE probing the version, so the probe itself is PATH-free."""
    pytest.importorskip("pytesseract")
    import pytesseract

    from desktop_worker.perception.backends import TesseractOcrBackend

    _clear_tesseract_env(monkeypatch)
    monkeypatch.setenv("TESSERACT_CMD", r"C:\resolved\tesseract.exe")
    monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda *a, **k: "5.4.0")
    TesseractOcrBackend()
    assert pytesseract.pytesseract.tesseract_cmd == r"C:\resolved\tesseract.exe"


def test_construction_falls_back_to_null_when_resolution_finds_nothing(monkeypatch):
    """Genuinely absent binary must still degrade to Null -- resolution failing
    must not change the existing fail-closed factory behaviour."""
    pytest.importorskip("pytesseract")
    import pytesseract

    from desktop_worker.perception.backends import NullOcrBackend, get_ocr_backend

    _clear_tesseract_env(monkeypatch)
    monkeypatch.setattr(shutil, "which", lambda name: None)

    def boom(*a, **k):
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(pytesseract, "get_tesseract_version", boom)
    assert isinstance(get_ocr_backend(True), NullOcrBackend)
