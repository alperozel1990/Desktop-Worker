"""Tests for offline Program -> PNG preview + montage."""

from desktop_worker.geometry.dsl import parse_program
from desktop_worker.geometry.preview import montage_png, render_program_png

_CAT = {"primitives": [
    {"kind": "circle", "center": [50, 42], "r": 22},
    {"kind": "polyline", "points": [[33, 24], [28, 8], [44, 28]], "closed": True},
    {"kind": "dot", "at": [50, 48]},
]}


def test_render_program_png_creates_image(tmp_path):
    dest = str(tmp_path / "cat.png")
    out = render_program_png(parse_program(_CAT), dest, size=256)
    # PIL is a test dependency here; if present we get a real non-empty PNG.
    assert out == dest
    assert (tmp_path / "cat.png").stat().st_size > 0


def test_montage_combines_candidates(tmp_path):
    paths = []
    for i in range(3):
        p = str(tmp_path / f"c{i}.png")
        render_program_png(parse_program(_CAT), p, size=128)
        paths.append(p)
    out = montage_png(paths, str(tmp_path / "sheet.png"), cell=128, cols=3)
    assert out == str(tmp_path / "sheet.png")
    assert (tmp_path / "sheet.png").stat().st_size > 0


def test_montage_empty_returns_none(tmp_path):
    assert montage_png([], str(tmp_path / "x.png")) is None
