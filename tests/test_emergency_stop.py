import pytest

from desktop_worker.safety.emergency_stop import EmergencyStop, EmergencyStopError


def test_check_passes_when_clear():
    es = EmergencyStop()
    es.check()  # no raise


def test_stop_raises():
    es = EmergencyStop()
    es.stop("halt now")
    assert es.is_stopped()
    with pytest.raises(EmergencyStopError):
        es.check()
    assert "halt now" in es.reason


def test_clear_resets():
    es = EmergencyStop()
    es.stop()
    es.clear()
    assert not es.is_stopped()
    es.check()


def test_file_sentinel_triggers_stop(tmp_path):
    f = tmp_path / "ESTOP"
    es = EmergencyStop(f)
    assert not es.is_stopped()
    f.write_text("external stop", encoding="utf-8")
    assert es.is_stopped()
    with pytest.raises(EmergencyStopError):
        es.check()


def test_stop_writes_sentinel_file(tmp_path):
    f = tmp_path / "ESTOP"
    es = EmergencyStop(f)
    es.stop("boom")
    assert f.exists()
    assert "boom" in f.read_text(encoding="utf-8")
    es.clear()
    assert not f.exists()
