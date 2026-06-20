"""Observer — builds structured observations (requirements section 6).

Assembles a :class:`Observation` from a desktop backend, optionally capturing a
screenshot artifact and persisting the observation JSON. Cursor position is
always included in observation metadata, as required.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from desktop_worker.observation.backends import DesktopBackend, get_desktop_backend
from desktop_worker.schema.observations import Observation


class Observer:
    def __init__(
        self,
        backend: Optional[DesktopBackend] = None,
        *,
        screenshots_dir: Optional[Path] = None,
        observations_dir: Optional[Path] = None,
    ) -> None:
        self.backend = backend or get_desktop_backend()
        self.screenshots_dir = Path(screenshots_dir) if screenshots_dir else None
        self.observations_dir = Path(observations_dir) if observations_dir else None
        self._counter = 0

    def observe(self, label: str = "step", *, screenshot: bool = True) -> Observation:
        """Capture a structured observation of current desktop state."""
        self._counter += 1
        n = self._counter

        screenshot_ref: Optional[str] = None
        if screenshot and self.screenshots_dir is not None:
            dest = self.screenshots_dir / f"{label}-{n:04d}.png"
            screenshot_ref = self.backend.capture_screenshot(dest)

        obs = Observation(
            screen=self.backend.screen(),
            cursor=self.backend.cursor(),
            activeWindow=self.backend.active_window(),
            windows=self.backend.visible_windows(),
            screenshotRef=screenshot_ref,
        )

        if self.observations_dir is not None:
            self.observations_dir.mkdir(parents=True, exist_ok=True)
            out = self.observations_dir / f"{label}-{n:04d}.json"
            out.write_text(json.dumps(obs.to_dict(), indent=2), encoding="utf-8")

        return obs
