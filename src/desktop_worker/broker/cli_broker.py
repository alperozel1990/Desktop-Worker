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
from typing import Callable, Optional

from desktop_worker.audit.log import AuditLog
from desktop_worker.broker.elevation import Elevator, get_elevator
from desktop_worker.broker.risk import classify_command
from desktop_worker.safety.emergency_stop import EmergencyStop
from desktop_worker.safety.policy import ApprovalRequest, PermissionPolicy
from desktop_worker.schema.results import CliResult
from desktop_worker.util import utc_now_iso

_TAIL_CHARS = 2000  # how much stdout/stderr to inline in the result

# Sentinel so callers can distinguish "auto-detect an elevator" (omit the arg)
# from "explicitly no elevation strategy" (pass elevator=None).
_AUTO_ELEVATOR = object()


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
        elevator: object = _AUTO_ELEVATOR,
        is_elevated: Optional[Callable[[], bool]] = None,
    ) -> None:
        self.audit = audit
        self.policy = policy
        self.cli_dir = Path(cli_artifacts_dir)
        self.estop = estop
        self.default_timeout_ms = default_timeout_ms
        # Per-command elevation strategy (DW-CLI-ELEVATE). Omitting the arg
        # auto-detects the real UAC elevator (None on non-Windows). Passing
        # elevator=None explicitly disables elevation, so the broker stays honest
        # and runs inline non-elevated rather than pretending to elevate.
        self.elevator: Optional[Elevator] = (
            get_elevator() if elevator is _AUTO_ELEVATOR else elevator  # type: ignore[assignment]
        )
        # Injectable admin-detection so the elevated path is deterministically
        # testable regardless of the test runner's actual token.
        self._is_elevated = is_elevated or is_process_elevated
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

    # --- launch (fire-and-forget GUI apps) -----------------------------
    def launch(self, command: str, cwd: str, *, agent: str = "system",
               role: str = "system") -> CliResult:
        """Launch a GUI app detached — gated + audited, but NEVER waits/captures.

        ``run`` captures stdout, so a launched GUI app inherits the pipe and the
        call blocks until the app CLOSES. For opening apps (notepad, Paint, a URL)
        use this: it redirects the child's handles to DEVNULL (no inheritance) and
        does not wait, so it returns immediately. Same classify+approval+audit gate.
        """
        if self.estop is not None:
            self.estop.check()
        command = command.strip()
        risk = classify_command(command)
        approved = False
        if self.policy.requires_approval(risk):
            approved = (command in self._session_allow) or self.policy.authorize(
                ApprovalRequest(kind="launch", summary=command, risk=risk,
                                detail={"cwd": cwd}))
            if not approved:
                return self._blocked(command, cwd, risk.value,
                                     "launch not approved by user", agent=agent, role=role)
        cwd_path = Path(cwd)
        if not cwd_path.exists() or not cwd_path.is_dir():
            return self._blocked(command, cwd, risk.value,
                                 f"working directory does not exist: {cwd}",
                                 agent=agent, role=role)
        now = utc_now_iso()
        try:
            subprocess.Popen(command, cwd=str(cwd_path), shell=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except OSError as exc:
            return self._blocked(command, cwd, risk.value,
                                 f"failed to launch: {exc}", agent=agent, role=role)
        result = CliResult(
            command=command, cwd=str(cwd_path), startedAt=now, endedAt=utc_now_iso(),
            exitCode=0, stdoutRef=None, stderrRef=None,
            elevated=False, riskLevel=risk.value, approvedByUser=approved,
            blocked=False, blockedReason=None, stdoutTail="(launched detached)",
        )
        self.history.append(result)
        self.audit.record("cli.launched", agent=agent, role=role,
                          cli=result.to_dict(),
                          approval={"required": self.policy.requires_approval(risk),
                                    "approved": approved})
        return result

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

        already_admin = bool(self._is_elevated())
        # Use the elevator only when elevation is requested AND we are not already
        # admin AND a strategy exists. If already admin, the inline run inherits
        # the elevated token. If elevation is requested but impossible, we run
        # inline non-elevated and report elevated=False (never overstate).
        use_elevator = bool(elevated) and not already_admin and self.elevator is not None

        if use_elevator:
            exit_code, timed_out, stdout_text, stderr_text, actually_elevated = (
                self._run_elevated(command, str(cwd_path), stdout_ref, stderr_ref,
                                   timeout_s=timeout_s, env=env)
            )
        else:
            exit_code, timed_out, stdout_text, stderr_text = self._run_inline(
                command, str(cwd_path), stdout_ref, stderr_ref,
                timeout_s=timeout_s, env=env,
            )
            actually_elevated = bool(elevated) and already_admin

        ended = utc_now_iso()

        result = CliResult(
            command=command,
            cwd=str(cwd_path),
            startedAt=started,
            endedAt=ended,
            exitCode=exit_code,
            stdoutRef=str(stdout_ref),
            stderrRef=str(stderr_ref),
            elevated=actually_elevated,
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

    # --- execution paths ----------------------------------------------
    def _run_inline(
        self, command: str, cwd: str, stdout_ref: Path, stderr_ref: Path,
        *, timeout_s: float, env: Optional[dict[str, str]],
    ) -> tuple[Optional[int], bool, str, str]:
        """Run in the current security context, capturing output to files.

        shell=True routes through cmd.exe so the AI can use normal command
        strings. This is acceptable *because* it is gated by classify + approval
        + audit upstream; it is not an open passthrough.
        """
        exit_code: Optional[int] = None
        timed_out = False
        stdout_text = ""
        stderr_text = ""
        try:
            proc = subprocess.run(
                command, cwd=cwd, shell=True, capture_output=True,
                text=True, timeout=timeout_s, env=env,
            )
            exit_code = proc.returncode
            stdout_text = proc.stdout or ""
            stderr_text = proc.stderr or ""
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout_text = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr_text = exc.stderr if isinstance(exc.stderr, str) else ""
            stderr_text += f"\n[broker] command timed out after {timeout_s:.0f}s"
        except OSError as exc:
            stderr_text = f"[broker] failed to launch command: {exc}"
        stdout_ref.write_text(stdout_text, encoding="utf-8")
        stderr_ref.write_text(stderr_text, encoding="utf-8")
        return exit_code, timed_out, stdout_text, stderr_text

    def _run_elevated(
        self, command: str, cwd: str, stdout_ref: Path, stderr_ref: Path,
        *, timeout_s: float, env: Optional[dict[str, str]],
    ) -> tuple[Optional[int], bool, str, str, bool]:
        """Run elevated via the injected strategy; the strategy writes the files."""
        run = self.elevator.run_elevated(
            command, cwd, stdout_ref, stderr_ref, timeout_s=timeout_s, env=env,
        )
        if not run.launched:
            # Elevation failed/declined: fall back to an honest inline run so the
            # command is not silently dropped, and report elevated=False.
            note = f"[broker] elevation failed ({run.error}); ran without elevation"
            ec, to, out, err = self._run_inline(
                command, cwd, stdout_ref, stderr_ref, timeout_s=timeout_s, env=env,
            )
            err = (err + "\n" + note).strip()
            stderr_ref.write_text(err, encoding="utf-8")
            return ec, to, out, err, False
        out = stdout_ref.read_text(encoding="utf-8") if stdout_ref.exists() else ""
        err = stderr_ref.read_text(encoding="utf-8") if stderr_ref.exists() else ""
        return run.exit_code, run.timed_out, out, err, True

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
