"""Tests for canvas detection (pure pieces; no display needed)."""

from desktop_worker.geometry.canvas import (CanvasRect, NullCanvasLocator,
                                            apply_inner_margin, client_to_canvas,
                                            fit_square, get_canvas_locator)


def test_fit_square_centers_and_preserves_aspect():
    # Wide canvas (1000x400) -> 400x400 square centered horizontally.
    sq = fit_square(CanvasRect(0, 0, 1000, 400, source="uia"))
    assert sq.width == sq.height == 400
    assert sq.left == 300 and sq.right == 700        # centered on x
    assert sq.top == 0 and sq.bottom == 400          # full height
    assert sq.source == "uia"


def test_null_locator_returns_fixed_rect():
    rect = NullCanvasLocator((100, 100, 900, 700)).locate()
    assert rect.as_tuple() == (100, 100, 900, 700)
    assert rect.source == "null"
    assert rect.width == 800 and rect.height == 600


def test_client_to_canvas_removes_ribbon_and_status():
    # 1000x800 client at screen origin (0,0).
    canvas = client_to_canvas((0, 0, 1000, 800))
    assert canvas.source == "client"
    # Top must be well below the ribbon band (>16% of 800 = 128px, then inner margin).
    assert canvas.top > 128
    # Canvas stays strictly inside the client area on every side.
    assert canvas.left > 0 and canvas.top > 0
    assert canvas.right < 1000 and canvas.bottom < 800
    assert canvas.width > 0 and canvas.height > 0


def test_apply_inner_margin_pulls_inward():
    rect = CanvasRect(0, 0, 100, 100, source="uia")
    pulled = apply_inner_margin(rect, 0.10)
    assert pulled.as_tuple() == (10, 10, 90, 90)
    assert pulled.source == "uia"          # source preserved


def test_factory_returns_null_when_not_real():
    locator = get_canvas_locator(prefer_real=False)
    assert isinstance(locator, NullCanvasLocator)
    assert locator.locate().source == "null"
