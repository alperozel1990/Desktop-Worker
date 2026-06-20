from desktop_worker.audit.log import AuditLog, redact


def test_record_and_read_roundtrip(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl", session_id="s1", task_id="t1")
    log.record("action.executed", agent="Claude Strategist", role="strategist",
               action={"type": "mouse.click"}, result={"success": True})
    entries = log.read_all()
    assert len(entries) == 1
    e = entries[0]
    assert e["event"] == "action.executed"
    assert e["sessionId"] == "s1"
    assert e["taskId"] == "t1"
    assert e["action"] == {"type": "mouse.click"}
    assert "timestamp" in e


def test_jsonl_is_one_line_per_entry(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    for i in range(3):
        log.record("e", detail={"i": i})
    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3


def test_redaction_basic():
    assert "***REDACTED***" in redact("password = hunter2")
    assert "hunter2" not in redact("password = hunter2")
    assert "***REDACTED_KEY***" in redact("sk-ABCDEFGH12345678")
    assert "***REDACTED***" in redact("Authorization: Bearer abc.def.ghi")


def test_redaction_applied_in_record(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    log.record("cli.executed", cli={"command": "set API_KEY=supersecretvalue"})
    raw = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "supersecretvalue" not in raw
    assert "REDACTED" in raw
