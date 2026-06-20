"""Elevated/admin-capable CLI broker (requirements section 11).

This broker is the single controlled execution boundary for ALL CLI work. The
AI cannot run commands any other way — there is no raw shell passthrough in the
codebase. Every command goes through the same pipeline:

    preview -> risk classify -> approval gate -> execute -> capture -> audit

Design notes on "elevated by default":
  * "Elevated" means the broker is *capable* of admin execution and reports
    whether the current process token is elevated. The intended deployment runs
    Desktop-Worker from an Administrator context (the start_dw_claude.bat
    launcher self-elevates via UAC), so commands inherit admin rights and their
    stdout/stderr/exit code can be captured normally.
  * Re-elevating an *individual* command via ShellExecute "runas" spawns a
    separate process whose output cannot be captured inline. That mechanism is
    deferred to a dedicated Phase 3 card (DW-CLI-ELEVATE) which will redirect the
    elevated child's output to the artifact files. Until then, true per-command
    re-elevation from a non-admin context is explicitly NOT silently performed —
    the broker records ``elevated: false`` so logs never overstate privilege.

What this file deliberately does NOT do: provide an unrestricted shell. There is
no method that runs an arbitrary command without classification, approval gating
and audit logging.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from desktop_worker.audit.log import AuditLog
from desktop_worker.broker.risk import classify_command
from desktop_worker.safety.emergency_stop import EmergencyStop
from desktop_worker.safety.policy import ApprovalRequest, PermissionPolicy
from desktop_worker.schema.results import CliResult
from desktop_worker.util import utc_now_iso

_TAIL_CHARS = 2000  # how much stdout/stderr to inline in the result


def is_process_elevated() -> bool:
    """Return True if the current process token is elevated (Windows admin).

    Returns False on non-Windows or if the check cannot be performed, so the
    broker never *over*-reports privilege.
    """
    try:
        import ctypes  # local import: avoids cost on non-Windows / unused paths

        return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
    except Exception:
        return False


class ElevatedCliBroker:
    """Controlled CLI execution boundary."""

    def __init__(
        self,
        *,
        audit: AuditLog,
        policy: PermissionPolicy,
        cli_artifacts_dir: Path,
        estop: Optional[EmergencyStop] = None,
        default_timeout_ms: int = 120_000,
    ) -> None:
        self.audit = audit
        self.policy = policy
        self.cli_dir = Path(cli_artifacts_dir)
        self.estop = estop
        self.default_timeout_ms = default_timeout_ms
        self._counter = 0
        self.history: list[CliResult] = []
        # Session-scoped allow rules: commands the user approved "for this
        # session" so identical high-risk commands need not re-prompt.
        self._session_allow: set[str] = set()

    # --- preview -------------------------------------------------------
    def preview(self, command: str, cwd: str) -> dict[str, object]:
        """Build a command preview (requirements section 11) without running."""
        risk = classify_command(command)
        return {
            "command": command,
            "cwd": cwd,
            "riskLevel": risk.value,
            "requiresApproval": self.policy.requires_approval(risk),
            "elevatedProcess": is_process_elevated(),
        }

    def allow_for_session(self, command: str) -> None:
        self._session_allow.add(command.strip())

    # --- run -----------------------------------------------------------
    def run(
        self,
        command: str,
        cwd: str,
        *,
        timeout_ms: Optional[int] = None,
        elevated: bool = True,
        env: Optional[dict[str, str]] = None,
        agent: str = "system",
        role: str = "system",
    ) -> CliResult:
        """Execute a command through the controlled boundary.

        ``elevated=True`` requests admin execution; the result reports the
        *actual* elevation achieved (the current process token's state).
        """
        if self.estop is not None:
            self.estop.check()

        command = command.strip()
        risk = classify_command(command)
        approved = False

        # --- approval gate (high-risk requires explicit user approval) ----
        if self.policy.requires_approval(risk):
            if command in self._session_allow:
                approved = True
            else:
                approved = self.policy.authorize(ApprovalRequest(
                    kind="cli", summary=command, risk=risk,
                    detail={"cwd": cwd, "elevated": elevated},
                ))
            if not approved:
                return self._blocked(command, cwd, risk.value,
                                     "high-risk command not approved by user",
                                     agent=agent, role=role)

        # --- working directory isolation (mandatory) ---------------------
        cwd_path = Path(cwd)
        if not cwd_path.exists() or not cwd_path.is_dir():
            return self._blocked(command, cwd, risk.value,
                                 f"working directory does not exist: {cwd}",
                                 agent=agent, role=role)

        self._counter += 1
        n = self._counter
        self.cli_dir.mkdir(parents=True, exist_ok=True)
        stdout_ref = self.cli_dir / f"{n:04d}.stdout.txt"
        stderr_ref = self.cli_dir / f"{n:04d}.stderr.txt"

        timeout_s = (timeout_ms or self.default_timeout_ms) / 1000.0
        started = utc_now_iso()
        exit_code: Optional[int] = None
        timed_out = False
        stdout_text = ""
        stderr_text = ""

        try:
            # shell=True routes through cmd.exe so the AI can use normal command
            # strings. This is acceptable *because* it is gated by classify +
            # approval + audit above; it is not an open passthrough.
            proc = subprocess.run(
                command,
                cwd=str(cwd_path),
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                env=env,
            )
            exit_code = proc.returncode
            stdout_text = proc.stdout or ""
            stderr_text = proc.stderr or ""
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout_text = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            stderr_text = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
            stderr_text += f"\n[broker] command timed out after {timeout_s:.0f}s"
        except OSError as exc:
            stderr_text = f"[broker] failed to launch command: {exc}"

        ended = utc_now_iso()
        stdout_ref.write_text(stdout_text, encoding="utf-8")
        stderr_ref.write_text(stderr_text, encoding="utf-8")

        result = CliResult(
            command=command,
            cwd=str(cwd_path),
            startedAt=started,
            endedAt=ended,
            exitCode=exit_code,
            stdoutRef=str(stdout_ref),
            stderrRef=str(stderr_ref),
            elevated=bool(elevated) and is_process_elevated(),
            riskLevel=risk.value,
            approvedByUser=approved,
            timedOut=timed_out,
            stdoutTail=stdout_text[-_TAIL_CHARS:],
            stderrTail=stderr_text[-_TAIL_CHARS:],
        )
        self.history.append(result)
        self.audit.record(
            "cli.executed", agent=agent, role=role,
            cli=result.to_dict(),
            approval={"required": self.policy.requires_approval(risk),
                      "approved": approved},
        )
        return result

    # --- helpers -------------------------------------------------------
    def _blocked(
        self, command: str, cwd: str, risk: str, reason: str,
        *, agent: str, role: str,
    ) -> CliResult:
        now = utc_now_iso()
        result = CliResult(
            command=command, cwd=cwd, startedAt=now, endedAt=now,
            exitCode=None, stdoutRef=None, stderrRef=None,
            elevated=False, riskLevel=risk, approvedByUser=False,
            blocked=True, blockedReason=reason,
        )
        self.history.append(result)
        self.audit.record(
            "cli.blocked", agent=agent, role=role,
            cli=result.to_dict(),
            approval={"required": True, "approved": False, "reason": reason},
        )
        return result
