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
    """Fake screenshot_fn writing a DISTINCT small PNG per call (realistic views)."""
    calls = []

    def shot(dest):
        i = len(calls)
        calls.append(str(dest))
        return _png(dest, color=((40 * i) % 256, 80, 120))

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


def test_orbit_is_eased_multistep_with_correct_total(tmp_path):
    tool, ib, _ = _tool(tmp_path)
    tool.run({"views": [[{"orbit": [200, -60]}]]})
    moves = [c for c in ib.calls if c[0] == "move_relative"]
    assert len(moves) > 1  # eased into sub-steps, not one instant jump
    assert sum(m[1] for m in moves) == 200   # exact net dx
    assert sum(m[2] for m in moves) == -60    # exact net dy
    kinds = [c[0] for c in ib.calls]
    assert kinds[0] == "mouse_down" and kinds[-1] == "mouse_up"


def test_crop_validated_and_applied(tmp_path):
    tool, _, _ = _tool(tmp_path)
    with pytest.raises(ToolError):
        tool.run({"views": [[{"key": "A"}]], "crop": [10, 10, 5, 5]})  # right<left
    out = tool.run({"views": [[{"key": "A"}]], "crop": [5, 5, 35, 25]})
    assert out["success"] is True and out["montage"]


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


def test_identical_views_warn(tmp_path):
    ib = NullInputBackend()
    calls = []

    def shot(dest):  # SAME image every call -> a view change didn't register
        calls.append(str(dest))
        return _png(dest, color=(100, 100, 100))

    tool = Inspect3DTool(input_backend=ib, screenshot_fn=shot, estop=EmergencyStop(),
                         work_dir=tmp_path / "i")
    out = tool.run({"views": [[{"key": "A"}], [{"key": "B"}], [{"key": "C"}]]})
    assert out["success"] is True
    assert out["distinct_views"] == 1
    assert out["note"] and "identical" in out["note"]


def test_distinct_views_no_identical_warning(tmp_path):
    tool, _, _ = _tool(tmp_path)  # varying shotter -> all tiles differ
    out = tool.run({"views": [[{"key": "A"}], [{"key": "B"}]]})
    assert out["distinct_views"] == 2
    assert not (out["note"] and "identical" in out["note"])


def test_cols_param_builds(tmp_path):
    tool, _, _ = _tool(tmp_path)
    out = tool.run({"views": [[{"key": k}] for k in "ABCD"], "cols": 2})
    assert out["success"] is True and out["montage"]


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
