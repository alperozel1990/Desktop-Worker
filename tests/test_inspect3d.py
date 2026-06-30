"""Tests for the inspect_3d multi-view 3D-perception tool (Tier 3, DW-3D-INSPECT)."""

import pytest

from desktop_worker.actions.backends import NullInputBackend
from desktop_worker.safety.emergency_stop import EmergencyStop
from desktop_worker.tools import Inspect3DTool, build_montage
from desktop_worker.tools.registry import ToolError


def _png(path, size=(40, 30), color=(120, 160, 200)):
    from PIL import Image
    Image.new("RGB", size, color).save(path)
    return str(path)


def _shotter(tmp_path):
    """Fake screenshot_fn that writes a small real PNG and returns its path."""
    calls = []

    def shot(dest):
        calls.append(str(dest))
        return _png(dest)

    return shot, calls


def _tool(tmp_path, *, estop=None):
    ib = NullInputBackend()
    shot, calls = _shotter(tmp_path)
    tool = Inspect3DTool(input_backend=ib, screenshot_fn=shot, estop=estop or EmergencyStop(),
                         work_dir=tmp_path / "inspect")
    return tool, ib, calls


def test_captures_views_and_builds_montage(tmp_path):
    tool, ib, calls = _tool(tmp_path)
    out = tool.run({"views": [[{"key": "KP_1"}], [{"key": "KP_3"}], [{"key": "KP_7"}]],
                    "labels": ["front", "side", "top"]})
    assert out["success"] is True
    assert out["views"] == 3
    assert len(out["tiles"]) == 3
    assert out["montage"] and out["montage"].endswith(".png")
    from pathlib import Path
    assert Path(out["montage"]).exists()
    # Each view's key press reached the input backend.
    assert ("press_key", ("KP_1",), {}) in ib.calls or any(
        c[0] == "press_key" for c in ib.calls)


def test_orbit_step_emits_middle_drag(tmp_path):
    tool, ib, calls = _tool(tmp_path)
    tool.run({"views": [[{"move": [500, 400]}, {"orbit": [200, -60]}]]})
    kinds = [c[0] for c in ib.calls]
    assert "mouse_down" in kinds and "move_relative" in kinds and "mouse_up" in kinds
    assert "move" in kinds


def test_grid_overlay_builds(tmp_path):
    tool, ib, calls = _tool(tmp_path)
    out = tool.run({"views": [[{"key": "KP_1"}]], "grid": 4})
    assert out["success"] is True and out["montage"]


def test_rejects_empty_or_too_many_views(tmp_path):
    tool, _, _ = _tool(tmp_path)
    with pytest.raises(ToolError):
        tool.run({"views": []})
    with pytest.raises(ToolError):
        tool.run({"views": [[{"key": "A"}]] * 7})


def test_rejects_unknown_step_and_bad_labels(tmp_path):
    tool, _, _ = _tool(tmp_path)
    with pytest.raises(ToolError):
        tool.run({"views": [[{"frobnicate": 1}]]})
    with pytest.raises(ToolError):
        tool.run({"views": [[{"key": "A"}]], "labels": ["a", "b"]})


def test_emergency_stop_aborts(tmp_path):
    estop = EmergencyStop(tmp_path / "ESTOP")
    estop.stop("test")
    tool, _, _ = _tool(tmp_path, estop=estop)
    with pytest.raises(ToolError, match="emergency stop"):
        tool.run({"views": [[{"key": "KP_1"}]]})


def test_build_montage_skips_non_images(tmp_path):
    # A non-image "tile" (placeholder .txt, like the Null backend) is skipped.
    txt = tmp_path / "ph.txt"
    txt.write_text("not an image")
    png = tmp_path / "real.png"
    _png(png)
    out = build_montage([str(txt), str(png)], ["a", "b"], 0, tmp_path / "m.png")
    assert out and out.endswith("m.png")
    # All-placeholder -> no montage.
    assert build_montage([str(txt)], ["a"], 0, tmp_path / "m2.png") is None
