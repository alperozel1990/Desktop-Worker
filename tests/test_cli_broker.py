import sys

from desktop_worker.audit.log import AuditLog
from desktop_worker.broker.cli_broker import ElevatedCliBroker
from desktop_worker.safety.policy import PermissionPolicy, auto_approve, deny_all


def _broker(tmp_path, approve=False):
    audit = AuditLog(tmp_path / "audit.jsonl")
    policy = PermissionPolicy(approval_callback=auto_approve if approve else deny_all)
    return ElevatedCliBroker(
        audit=audit, policy=policy, cli_artifacts_dir=tmp_path / "cli"
    )


def test_low_risk_command_runs_and_captures(tmp_path):
    broker = _broker(tmp_path)
    res = broker.run("echo hello-broker", str(tmp_path))
    assert res.blocked is False
    assert res.exitCode == 0
    assert "hello-broker" in res.stdoutTail
    assert res.stdoutRef and (tmp_path / "cli").exists()
    # artifact files written
    assert "hello-broker" in (tmp_path / "cli" / "0001.stdout.txt").read_text()


def test_high_risk_blocked_without_approval(tmp_path):
    broker = _broker(tmp_path, approve=False)
    res = broker.run("del something.txt", str(tmp_path))
    assert res.blocked is True
    assert res.exitCode is None
    assert "not approved" in (res.blockedReason or "")


def test_high_risk_allowed_with_approval_runs(tmp_path):
    broker = _broker(tmp_path, approve=True)
    # Use a harmless command the classifier rates HIGH ("net user" matches).
    res = broker.run("echo net user noop", str(tmp_path))
    # echo makes it safe; classifier sees "net user" -> high -> needs approval.
    assert res.riskLevel == "high"
    assert res.approvedByUser is True
    assert res.blocked is False


def test_missing_cwd_blocks(tmp_path):
    broker = _broker(tmp_path)
    res = broker.run("echo hi", str(tmp_path / "does-not-exist"))
    assert res.blocked is True
    assert "working directory" in (res.blockedReason or "")


def test_preview_does_not_execute(tmp_path):
    broker = _broker(tmp_path)
    prev = broker.preview("del x.txt", str(tmp_path))
    assert prev["riskLevel"] == "high"
    assert prev["requiresApproval"] is True
    assert broker.history == []  # nothing ran


def test_timeout(tmp_path):
    broker = _broker(tmp_path)
    # A command that sleeps longer than the timeout.
    if sys.platform.startswith("win"):
        cmd = "ping 127.0.0.1 -n 5 > nul"
    else:
        cmd = "sleep 5"
    res = broker.run(cmd, str(tmp_path), timeout_ms=300)
    assert res.timedOut is True


def test_history_and_audit_recorded(tmp_path):
    broker = _broker(tmp_path)
    broker.run("echo a", str(tmp_path))
    broker.run("echo b", str(tmp_path))
    assert len(broker.history) == 2
    events = [e["event"] for e in broker.audit.read_all()]
    assert events.count("cli.executed") == 2
