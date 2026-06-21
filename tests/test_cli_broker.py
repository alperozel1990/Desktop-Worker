import sys
from pathlib import Path

from desktop_worker.audit.log import AuditLog
from desktop_worker.broker.cli_broker import ElevatedCliBroker
from desktop_worker.broker.elevation import ElevatedRun
from desktop_worker.safety.policy import PermissionPolicy, auto_approve, deny_all


def _broker(tmp_path, approve=False, *, elevator=None, is_elevated=None):
    # IMPORTANT: default elevator=None so the test suite NEVER constructs the
    # real WindowsElevator (which would pop a UAC prompt when run non-elevated).
    # Tests that exercise elevation pass an explicit FakeElevator.
    audit = AuditLog(tmp_path / "audit.jsonl")
    policy = PermissionPolicy(approval_callback=auto_approve if approve else deny_all)
    kwargs = {"elevator": elevator}
    if is_elevated is not None:
        kwargs["is_elevated"] = is_elevated
    return ElevatedCliBroker(
        audit=audit, policy=policy, cli_artifacts_dir=tmp_path / "cli", **kwargs
    )


class FakeElevator:
    """Simulates UAC elevation by writing the output files directly."""

    def __init__(self, exit_code=0, timed_out=False, launched=True, out="elevated-out"):
        self.calls = []
        self._ec = exit_code
        self._to = timed_out
        self._launched = launched
        self._out = out

    def run_elevated(self, command, cwd, stdout_path, stderr_path, *, timeout_s, env=None):
        Path(stdout_path).write_text(self._out, encoding="utf-8")
        Path(stderr_path).write_text("", encoding="utf-8")
        self.calls.append(command)
        return ElevatedRun(exit_code=self._ec, timed_out=self._to, launched=self._launched)


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


def test_launch_is_nonblocking_and_audited(tmp_path):
    # `launch` must return immediately (no wait/capture) and be audited. Use a
    # command that would BLOCK under run() if its output were captured.
    broker = _broker(tmp_path)
    import time
    if sys.platform.startswith("win"):
        cmd = 'start "" cmd /c "ping 127.0.0.1 -n 3 >nul"'
    else:
        cmd = "sleep 3 &"
    t = time.time()
    res = broker.launch(cmd, str(tmp_path))
    assert time.time() - t < 2.0          # returned immediately, did not wait
    assert res.blocked is False
    assert "cli.launched" in [e["event"] for e in broker.audit.read_all()]


def test_launch_blocked_when_cwd_missing(tmp_path):
    broker = _broker(tmp_path)
    res = broker.launch('start "" notepad', str(tmp_path / "nope"))
    assert res.blocked is True


# --- DW-CLI-ELEVATE: per-command elevation -------------------------------

def test_elevated_path_uses_elevator_when_not_admin(tmp_path):
    fake = FakeElevator(exit_code=0)
    broker = _broker(tmp_path, approve=True, elevator=fake, is_elevated=lambda: False)
    res = broker.run("echo hi", str(tmp_path), elevated=True)
    assert fake.calls == ["echo hi"]      # actually went through the elevator
    assert res.elevated is True
    assert res.exitCode == 0
    assert "elevated-out" in res.stdoutTail


def test_admin_runs_inline_without_elevator(tmp_path):
    fake = FakeElevator()
    broker = _broker(tmp_path, elevator=fake, is_elevated=lambda: True)
    res = broker.run("echo inline", str(tmp_path), elevated=True)
    assert fake.calls == []               # already admin -> inline, no re-elevation
    assert res.elevated is True
    assert "inline" in res.stdoutTail


def test_not_admin_no_elevator_is_honest(tmp_path):
    # No elevator available + not admin: still runs (non-elevated) and is HONEST.
    broker = _broker(tmp_path, elevator=None, is_elevated=lambda: False)
    res = broker.run("echo x", str(tmp_path), elevated=True)
    assert res.elevated is False          # never overstates privilege
    assert "x" in res.stdoutTail          # but the command still ran + captured


def test_elevated_false_never_elevates(tmp_path):
    fake = FakeElevator()
    broker = _broker(tmp_path, elevator=fake, is_elevated=lambda: True)
    res = broker.run("echo y", str(tmp_path), elevated=False)
    assert fake.calls == []
    assert res.elevated is False


def test_elevated_timeout_reported(tmp_path):
    fake = FakeElevator(exit_code=None, timed_out=True)
    broker = _broker(tmp_path, approve=True, elevator=fake, is_elevated=lambda: False)
    res = broker.run("echo slow", str(tmp_path), elevated=True)
    assert res.timedOut is True
    assert res.exitCode is None
    assert res.elevated is True           # it did launch elevated


def test_uac_declined_falls_back_inline_and_is_honest(tmp_path):
    # Elevator could not launch (UAC declined): command must still run inline,
    # report elevated=False, and not be silently dropped.
    fake = FakeElevator(launched=False)
    broker = _broker(tmp_path, approve=True, elevator=fake, is_elevated=lambda: False)
    res = broker.run("echo recover", str(tmp_path), elevated=True)
    assert res.elevated is False
    assert "recover" in res.stdoutTail    # ran inline as fallback
    assert "elevation failed" in res.stderrTail


def test_elevated_flag_is_audited(tmp_path):
    fake = FakeElevator(exit_code=0)
    broker = _broker(tmp_path, approve=True, elevator=fake, is_elevated=lambda: False)
    broker.run("echo audited", str(tmp_path), elevated=True)
    rec = [e for e in broker.audit.read_all() if e["event"] == "cli.executed"][-1]
    assert rec["cli"]["elevated"] is True
