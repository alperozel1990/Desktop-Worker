"""Per-command elevation strategy for the CLI broker (DW-CLI-ELEVATE).

Re-launching a *single* command elevated requires UAC consent and spawns a
separate process whose console output cannot be captured inline. The strategy
here wraps the command in a temporary batch file that redirects stdout/stderr to
the broker's artifact files and writes the exit code to a sentinel file, launches
that wrapper elevated via ShellExecuteEx "runas", waits for it, and recovers the
exit code from the sentinel.

The :class:`Elevator` interface is injectable so the broker's elevated path is
fully unit-testable with a fake elevator — the real :class:`WindowsElevator`
(which pops a UAC prompt) only runs on Windows and is validated manually.

Known limitations (documented, not silently ignored):
  * A non-admin parent cannot terminate an elevated child, so on timeout the
    elevated command is reported as timed out but may keep running.
  * Environment overrides are applied as ``set`` lines in the wrapper.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable


@dataclass
class ElevatedRun:
    """Outcome of an elevated command execution."""

    exit_code: Optional[int]
    timed_out: bool = False
    launched: bool = False        # did the elevated process actually start?
    error: Optional[str] = None


@runtime_checkable
class Elevator(Protocol):
    """Runs one command elevated, redirecting output to the given files."""

    def run_elevated(
        self,
        command: str,
        cwd: str,
        stdout_path: Path,
        stderr_path: Path,
        *,
        timeout_s: float,
        env: Optional[dict[str, str]] = None,
    ) -> ElevatedRun:
        ...


class WindowsElevator:
    """Real UAC elevation via ShellExecuteEx "runas". Windows only."""

    def __init__(self) -> None:
        import sys

        if not sys.platform.startswith("win"):
            raise RuntimeError("WindowsElevator requires Windows")
        import ctypes  # noqa: F401  (probe so the factory can fall back)

        self._ctypes = ctypes

    def run_elevated(
        self,
        command: str,
        cwd: str,
        stdout_path: Path,
        stderr_path: Path,
        *,
        timeout_s: float,
        env: Optional[dict[str, str]] = None,
    ) -> ElevatedRun:
        import os
        import tempfile

        ctypes = self._ctypes

        stdout_path = Path(stdout_path)
        stderr_path = Path(stderr_path)
        # Pre-create the output files so a tail read never fails.
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")

        # SECURITY: the wrapper .bat runs ELEVATED, so its path/content must not
        # be attacker-pre-plantable. Create both helper files atomically with
        # unpredictable names (mkstemp, O_EXCL) inside the app-controlled
        # artifacts directory — never the world-readable global %TEMP%.
        helper_dir = stdout_path.parent
        bat_fd, bat_name = tempfile.mkstemp(suffix=".bat", prefix="dw_elev_", dir=helper_dir)
        os.close(bat_fd)
        exit_fd, exit_name = tempfile.mkstemp(suffix=".txt", prefix="dw_exit_", dir=helper_dir)
        os.close(exit_fd)
        bat_file = Path(bat_name)
        exit_file = Path(exit_name)

        # NOTE: `command`, `cwd`, and env values are embedded verbatim. They are
        # already risk-classified + approval-gated upstream; a literal `"` in
        # them can still corrupt capture (best-effort), not escalate privilege.
        env_lines = ""
        if env:
            env_lines = "".join(f'set "{k}={v}"\r\n' for k, v in env.items())
        bat = (
            "@echo off\r\n"
            f'cd /d "{cwd}"\r\n'
            f"{env_lines}"
            f'{command} > "{stdout_path}" 2> "{stderr_path}"\r\n'
            f'echo %ERRORLEVEL% > "{exit_file}"\r\n'
        )
        # cmd.exe reads .bat in the OEM/ANSI codepage, not UTF-8. Use mbcs so
        # non-ASCII commands/paths are not mojibaked.
        bat_file.write_text(bat, encoding="mbcs", errors="replace")

        try:
            try:
                handle = self._shell_execute_runas("cmd.exe", f'/c ""{bat_file}""')
            except OSError as exc:
                return ElevatedRun(exit_code=None, launched=False, error=str(exc))
            if not handle:
                return ElevatedRun(
                    exit_code=None, launched=False,
                    error="ShellExecuteEx returned no process handle (UAC declined/failed)",
                )

            WAIT_TIMEOUT = 0x00000102
            try:
                wait = ctypes.windll.kernel32.WaitForSingleObject(
                    handle, int(timeout_s * 1000)
                )
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)

            if wait == WAIT_TIMEOUT:
                # A non-admin parent cannot kill the elevated child (documented).
                return ElevatedRun(exit_code=None, timed_out=True, launched=True)

            exit_code: Optional[int] = None
            if exit_file.exists():
                try:
                    exit_code = int(exit_file.read_text(encoding="mbcs").strip())
                except (ValueError, OSError):
                    exit_code = None
            return ElevatedRun(exit_code=exit_code, launched=True)
        finally:
            # Always clean up helper files — including on timeout / early return.
            for p in (bat_file, exit_file):
                try:
                    p.unlink()
                except OSError:
                    pass

    def _shell_execute_runas(self, file: str, params: str):
        ctypes = self._ctypes
        from ctypes import wintypes

        class SHELLEXECUTEINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("fMask", ctypes.c_ulong),
                ("hwnd", wintypes.HWND),
                ("lpVerb", wintypes.LPCWSTR),
                ("lpFile", wintypes.LPCWSTR),
                ("lpParameters", wintypes.LPCWSTR),
                ("lpDirectory", wintypes.LPCWSTR),
                ("nShow", ctypes.c_int),
                ("hInstApp", wintypes.HINSTANCE),
                ("lpIDList", ctypes.c_void_p),
                ("lpClass", wintypes.LPCWSTR),
                ("hkeyClass", wintypes.HKEY),
                ("dwHotKey", wintypes.DWORD),
                ("hIconOrMonitor", wintypes.HANDLE),
                ("hProcess", wintypes.HANDLE),
            ]

        SEE_MASK_NOCLOSEPROCESS = 0x00000040
        SW_HIDE = 0
        sei = SHELLEXECUTEINFO()
        sei.cbSize = ctypes.sizeof(sei)
        sei.fMask = SEE_MASK_NOCLOSEPROCESS
        sei.lpVerb = "runas"
        sei.lpFile = file
        sei.lpParameters = params
        sei.nShow = SW_HIDE
        # use_last_error so GetLastError reflects ShellExecuteExW, not stale state.
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        if not shell32.ShellExecuteExW(ctypes.byref(sei)):
            err = ctypes.get_last_error()
            raise OSError(err or 0, f"ShellExecuteExW failed (error {err})")
        return sei.hProcess


def get_elevator() -> Optional[Elevator]:
    """Return a real elevator if available, else None (caller stays honest)."""
    try:
        return WindowsElevator()
    except Exception:
        return None
