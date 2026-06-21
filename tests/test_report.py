"""Tests for the HTML session-replay report (pure builder + file round-trip)."""

import json

from desktop_worker.audit.report import build_html_report, write_html_report


def _entries():
    return [
        {"event": "task.started", "sessionId": "s1", "taskId": "t1",
         "timestamp": "2026-06-21T10:00:00.000000+00:00", "agent": "system"},
        {"event": "planner.step", "sessionId": "s1", "taskId": "t1",
         "timestamp": "2026-06-21T10:00:01.000000+00:00", "agent": "Claude CLI Planner",
         "reasoning": "open the Run dialog", "vision": False,
         "planned": {"action": {"type": "keyboard.hotkey", "keys": ["WIN", "R"]}}},
        {"event": "step.completed", "sessionId": "s1", "taskId": "t1",
         "timestamp": "2026-06-21T10:00:02.000000+00:00", "agent": "system",
         "result": {"success": True}, "verification": {"passed": True, "method": "visibleText"}},
        {"event": "task.finished", "sessionId": "s1", "taskId": "t1",
         "timestamp": "2026-06-21T10:00:03.000000+00:00", "agent": "system",
         "result": {"completed": True}},
    ]


def test_report_contains_decisions_and_status():
    html = build_html_report(_entries(), title="My run")
    assert "My run" in html
    assert "open the Run dialog" in html        # AI reasoning shown
    assert "keyboard.hotkey" in html            # action shown
    assert "completed" in html                  # final status
    assert "1 AI decisions" in html and "1 steps" in html
    assert html.strip().startswith("<!DOCTYPE html>")


def test_report_escapes_html():
    entries = [{"event": "planner.step", "timestamp": "2026-06-21T10:00:00.000000+00:00",
                "agent": "x", "reasoning": "<script>alert(1)</script>",
                "planned": {"action": {"type": "wait"}}}]
    html = build_html_report(entries)
    assert "<script>alert(1)</script>" not in html       # escaped
    assert "&lt;script&gt;" in html


def test_report_empty_is_valid():
    html = build_html_report([])
    assert "<!DOCTYPE html>" in html
    assert "in progress" in html


def test_write_html_report_roundtrip(tmp_path):
    (tmp_path / "audit.jsonl").write_text(
        "\n".join(json.dumps(e) for e in _entries()), encoding="utf-8")
    out = write_html_report(tmp_path / "audit.jsonl", tmp_path / "replay.html")
    assert out.exists()
    assert "keyboard.hotkey" in out.read_text(encoding="utf-8")


def test_report_survives_bad_timestamp():
    # A corrupt record (non-string timestamp) must not crash the whole replay.
    entries = [{"event": "planner.step", "timestamp": None, "agent": "x",
                "reasoning": "ok", "planned": {"action": {"type": "wait"}}},
               {"event": "task.finished", "timestamp": 12345,
                "result": {"completed": True}}]
    html = build_html_report(entries)
    assert "<!DOCTYPE html>" in html


def test_write_html_report_missing_audit(tmp_path):
    out = write_html_report(tmp_path / "nope.jsonl", tmp_path / "r.html")
    assert out.exists()                         # produces a valid empty report
