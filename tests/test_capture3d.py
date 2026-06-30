"""Tests for the Tier-2 3D tools: orbit + capture_burst."""

import pytest

from desktop_worker.actions.backends import NullInputBackend
from desktop_worker.safety.emergency_stop import EmergencyStop
from desktop_worker.tools import CaptureBurstTool, OrbitTool
from desktop_worker.tools.registry import ToolError


def _png(path, i=0):
    from PIL import Image
    Image.new("RGB", (40, 30), ((40 * i) % 256, 80, 120)).save(path)
    return str(path)


def _shotter():
    calls = []

    def shot(dest):
        i = len(calls)
        calls.append(str(dest))
        return _png(dest, i)

    return shot, calls


# --- orbit ---------------------------------------------------------------
def test_orbit_eased_with_move_first():
    ib = NullInputBackend()
    tool = OrbitTool(input_backend=ib, estop=EmergencyStop())
    out = tool.run({"delta": [240, -80], "move": [500, 400], "steps": 8})
    assert out["success"] is True
    kinds = [c[0] for c in ib.calls]
    assert kinds[0] == "move"                       # cursor moved into the viewport first
    assert kinds[1] == "mouse_down"
    moves = [c for c in ib.calls if c[0] == "move_relative"]
    assert len(moves) > 1
    assert sum(m[1] for m in moves) == 240 and sum(m[2] for m in moves) == -80
    assert kinds[-1] == "mouse_up"


def test_orbit_rejects_bad_delta():
    tool = OrbitTool(input_backend=NullInputBackend())
    with pytest.raises(ToolError):
        tool.run({"delta": [1, 2, 3]})


def test_orbit_estop_aborts(tmp_path):
    estop = EmergencyStop(tmp_path / "ESTOP"); estop.stop("x")
    tool = OrbitTool(input_backend=NullInputBackend(), estop=estop)
    with pytest.raises(ToolError, match="emergency stop"):
        tool.run({"delta": [10, 0]})


# --- capture_burst -------------------------------------------------------
def _burst(tmp_path, estop=None):
    ib = NullInputBackend()
    shot, calls = _shotter()
    tool = CaptureBurstTool(input_backend=ib, screenshot_fn=shot,
                            estop=estop or EmergencyStop(), work_dir=tmp_path / "burst")
    return tool, ib, calls


def test_capture_burst_frames_timestamps_montage(tmp_path):
    tool, ib, calls = _burst(tmp_path)
    out = tool.run({"orbit": [300, 0], "frames": 4, "move": [500, 400]})
    assert out["success"] is True
    assert out["count"] == 4                       # 1 initial + 3 sub-step frames
    assert len(out["frames"]) == 4
    assert len(out["timestamps_ms"]) == 4
    assert out["timestamps_ms"] == sorted(out["timestamps_ms"])  # monotonic
    assert out["montage"] and out["montage"].endswith(".png")
    # The orbit ran while the middle button was held across the whole burst.
    kinds = [c[0] for c in ib.calls]
    assert kinds.count("mouse_down") == 1 and kinds.count("mouse_up") == 1


def test_capture_burst_rejects_bad_frames(tmp_path):
    tool, _, _ = _burst(tmp_path)
    with pytest.raises(ToolError):
        tool.run({"orbit": [100, 0], "frames": 1})
    with pytest.raises(ToolError):
        tool.run({"orbit": [100, 0], "frames": 99})


def test_capture_burst_no_fast_without_dxcam(tmp_path):
    tool, _, _ = _burst(tmp_path)
    out = tool.run({"orbit": [120, 0], "frames": 3, "fast": True})
    # dxcam isn't installed in test env -> falls back to the injected screenshot path.
    assert out["success"] is True and out["fast"] is False and out["count"] == 3
