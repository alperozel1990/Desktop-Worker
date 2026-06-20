"""Session wiring — assembles all layers into a ready-to-run worker.

One place that constructs the audit log, safety controller, policy, broker,
observer, executor and loop with consistent config. Backends default to "real
if available, else Null" so the same code path runs on a developer's Windows
desktop and in headless CI.
"""

from __future__ import annotations

from typing import Optional

from desktop_worker.actions.backends import InputBackend, get_input_backend
from desktop_worker.actions.executor import ActionExecutor
from desktop_worker.audit.log import AuditLog
from desktop_worker.broker.cli_broker import ElevatedCliBroker
from desktop_worker.config import Config
from desktop_worker.observation.backends import DesktopBackend, get_desktop_backend
from desktop_worker.observation.observer import Observer
from desktop_worker.safety.emergency_stop import EmergencyStop
from desktop_worker.safety.policy import PermissionPolicy, deny_all


class Session:
    """A configured Desktop-Worker session (one session/task scope)."""

    def __init__(
        self,
        config: Optional[Config] = None,
        *,
        policy: Optional[PermissionPolicy] = None,
        desktop_backend: Optional[DesktopBackend] = None,
        input_backend: Optional[InputBackend] = None,
        prefer_real_backends: bool = True,
    ) -> None:
        self.config = config or Config()
        self.config.ensure_dirs()

        self.estop = EmergencyStop(self.config.estop_file)
        self.policy = policy or PermissionPolicy(approval_callback=deny_all)
        self.audit = AuditLog(
            self.config.audit_file,
            session_id=self.config.session_id,
            task_id=self.config.task_id,
        )

        self.desktop_backend = desktop_backend or get_desktop_backend(prefer_real_backends)
        self.input_backend = input_backend or get_input_backend(prefer_real_backends)

        self.observer = Observer(
            self.desktop_backend,
            screenshots_dir=self.config.screenshots_dir,
            observations_dir=self.config.observations_dir,
        )
        self.broker = ElevatedCliBroker(
            audit=self.audit,
            policy=self.policy,
            cli_artifacts_dir=self.config.cli_dir,
            estop=self.estop,
        )
        self.executor = ActionExecutor(
            audit=self.audit,
            policy=self.policy,
            input_backend=self.input_backend,
            broker=self.broker,
            estop=self.estop,
            dry_run=self.config.dry_run,
        )

    def backend_names(self) -> dict[str, str]:
        return {
            "desktop": type(self.desktop_backend).__name__,
            "input": type(self.input_backend).__name__,
        }
