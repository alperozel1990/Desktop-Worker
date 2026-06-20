"""Runtime configuration and artifact path layout.

Artifacts are organized by session and task exactly as required by the
requirements (section 17):

    artifacts/sessions/<session-id>/<task-id>/
        screenshots/
        observations/
        cli/
        audit.jsonl
        report.md
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Repository root = two levels up from this file (src/desktop_worker/config.py).
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACTS_ROOT = REPO_ROOT / "artifacts"

# Sentinel file polled by the emergency-stop mechanism. An external process
# (e.g. status_dw.bat or a future UI) can create this file to halt execution
# even if it cannot reach the in-process event.
DEFAULT_ESTOP_FILE = DEFAULT_ARTIFACTS_ROOT / "EMERGENCY_STOP"


@dataclass(frozen=True)
class Limits:
    """Hard safety limits applied per task (requirements section 12)."""

    max_retries: int = 3
    max_actions_per_task: int = 200
    max_task_seconds: int = 1800  # 30 minutes


@dataclass
class Config:
    """Top-level runtime configuration."""

    session_id: str = "session-001"
    task_id: str = "task-001"
    artifacts_root: Path = DEFAULT_ARTIFACTS_ROOT
    estop_file: Path = DEFAULT_ESTOP_FILE
    limits: Limits = field(default_factory=Limits)

    # Safety modes (requirements section 12).
    dry_run: bool = False          # validate + log, never actually execute
    explain_before_execute: bool = False

    @property
    def task_dir(self) -> Path:
        return self.artifacts_root / "sessions" / self.session_id / self.task_id

    @property
    def screenshots_dir(self) -> Path:
        return self.task_dir / "screenshots"

    @property
    def observations_dir(self) -> Path:
        return self.task_dir / "observations"

    @property
    def cli_dir(self) -> Path:
        return self.task_dir / "cli"

    @property
    def audit_file(self) -> Path:
        return self.task_dir / "audit.jsonl"

    @property
    def report_file(self) -> Path:
        return self.task_dir / "report.md"

    def ensure_dirs(self) -> None:
        """Create the artifact directory tree for this session/task."""
        for d in (self.screenshots_dir, self.observations_dir, self.cli_dir):
            d.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "Config":
        """Build config from environment, falling back to defaults."""
        return cls(
            session_id=os.environ.get("DW_SESSION_ID", "session-001"),
            task_id=os.environ.get("DW_TASK_ID", "task-001"),
            dry_run=os.environ.get("DW_DRY_RUN", "0") == "1",
        )
