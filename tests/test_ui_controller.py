"""Tests for the pure UI controller (Phase 7). No Tkinter, no display."""

import threading
import time

from desktop_worker.audit.log import AuditLog
from desktop_worker.config import Config
from desktop_worker.safety.emergency_stop import EmergencyStop
from desktop_worker.ui import ApprovalQueue, UiController, summarize_event


def _cfg(tmp_path):
    return Config(session_id="s", task_id="t", artifacts_root=tmp_path,
                  estop_file=tmp_path / "ESTOP")


def _controller(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.ensure_dirs()
    estop = EmergencyStop(cfg.estop_file)
    return UiController(cfg, estop), cfg, estop


# --- timeline / artifacts -------------------------------------------------

def test_timeline_reads_audit(tmp_path):
    c, cfg, _ = _controller(tmp_path)
    audit = AuditLog(cfg.audit_file, session_id="s", task_id="t")
    audit.record("step.planned", agent="Claude", action={"type": "mouse.click"})
    audit.record("task.completed")
    tl = c.timeline()
    assert [r["event"] for r in tl] == ["step.planned", "task.completed"]
    lines = c.timeline_lines()
    assert "step.planned" in lines[0] and "mouse.click" in lines[0]


def test_timeline_empty_when_no_log(tmp_path):
    c, _, _ = _controller(tmp_path)
    assert c.timeline() == []


def test_screenshots_and_reports(tmp_path):
    c, cfg, _ = _controller(tmp_path)
    (cfg.screenshots_dir / "a.png").write_bytes(b"x")
    (cfg.task_dir / "replay.html").write_text("<html>", encoding="utf-8")
    assert any(p.endswith("a.png") for p in c.screenshots())
    assert any(p.endswith("replay.html") for p in c.reports())


def test_summarize_event_cli():
    line = summarize_event({"timestamp": "2026-06-24T01:02:03Z", "event": "cli.executed",
                            "cli": {"command": "dir"}})
    assert "01:02:03" in line and "cli.executed" in line and "dir" in line


# --- safety controls ------------------------------------------------------

def test_estop_and_clear(tmp_path):
    c, _, estop = _controller(tmp_path)
    assert not c.is_stopped()
    c.estop("ui button")
    assert c.is_stopped() and estop.is_stopped()
    c.clear_stop()
    assert not c.is_stopped()


def test_pause_resume(tmp_path):
    c, _, _ = _controller(tmp_path)
    c.pause()
    assert c.is_paused()
    c.resume()
    assert not c.is_paused()


# --- task submission ------------------------------------------------------

def test_submit_and_pop_task(tmp_path):
    c, _, _ = _controller(tmp_path)
    assert c.pop_task() is None
    c.submit_task("  open notepad  ")
    assert c.pop_task() == "open notepad"
    assert c.pop_task() is None  # consumed once


# --- approval handshake ---------------------------------------------------

def test_approval_queue_approve():
    q = ApprovalQueue()
    result = {}

    def worker():
        result["decision"] = q.request("req-1", timeout=2.0)

    th = threading.Thread(target=worker)
    th.start()
    # Wait for the request to register, then approve.
    for _ in range(100):
        if q.pending() is not None:
            break
        time.sleep(0.01)
    assert q.pending() == "req-1"
    q.resolve(True)
    th.join(timeout=2.0)
    assert result["decision"] is True
    assert q.pending() is None  # cleared after resolution


def test_approval_queue_denies_on_timeout():
    q = ApprovalQueue()
    assert q.request("req", timeout=0.05) is False  # nobody resolved -> deny


def test_approval_queue_serializes_concurrent_requests():
    q = ApprovalQueue()
    # First requester holds the slot (waiting for a decision)...
    t1 = threading.Thread(target=lambda: q.request("first", timeout=1.0))
    t1.start()
    for _ in range(100):
        if q.pending() == "first":
            break
        time.sleep(0.01)
    # ...so a second requester cannot grab the slot and denies on its timeout.
    assert q.request("second", timeout=0.05) is False
    q.resolve(True)
    t1.join(timeout=2.0)


def test_controller_approve_resolves(tmp_path):
    c, _, _ = _controller(tmp_path)
    out = {}

    def worker():
        out["d"] = c.approve("the-request", timeout=2.0)

    th = threading.Thread(target=worker)
    th.start()
    for _ in range(100):
        if c.pending_approval() is not None:
            break
        time.sleep(0.01)
    assert c.pending_approval() == "the-request"
    c.resolve_approval(False)  # deny
    th.join(timeout=2.0)
    assert out["d"] is False
