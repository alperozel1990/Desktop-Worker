"""Audit log (requirements section 13).

Every meaningful operation is appended as one JSON object per line (JSONL):
machine-readable for replay/analysis and human-readable for inspection.
Known secret patterns are redacted before writing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from desktop_worker.util import utc_now_iso

# Conservative secret-redaction patterns (requirements section 18). These cover
# common cases; the redaction list is expected to grow. Order matters: more
# specific patterns first.
_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)\b(api[_-]?key|secret|token|password|passwd|pwd)\b(\s*[:=]\s*)(\S+)"),
     r"\1\2***REDACTED***"),
    (re.compile(r"\b(sk-[A-Za-z0-9]{8,})\b"), "***REDACTED_KEY***"),
    (re.compile(r"\b(ghp_[A-Za-z0-9]{20,})\b"), "***REDACTED_TOKEN***"),
    (re.compile(r"\b(AKIA[0-9A-Z]{16})\b"), "***REDACTED_AWS_KEY***"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+"), "Bearer ***REDACTED***"),
)


def redact(text: str) -> str:
    """Redact known secret patterns from a string."""
    if not isinstance(text, str):
        return text
    out = text
    for pattern, repl in _REDACTIONS:
        out = pattern.sub(repl, out)
    return out


def _redact_obj(obj: Any) -> Any:
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, dict):
        return {k: _redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_redact_obj(v) for v in obj]
    return obj


class AuditLog:
    """Append-only JSONL audit log scoped to one session/task."""

    def __init__(
        self,
        path: Path,
        *,
        session_id: str = "session-001",
        task_id: str = "task-001",
        redact_secrets: bool = True,
    ) -> None:
        self.path = Path(path)
        self.session_id = session_id
        self.task_id = task_id
        self.redact_secrets = redact_secrets
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        event: str,
        *,
        agent: str = "system",
        role: str = "system",
        action: Optional[dict[str, Any]] = None,
        result: Optional[dict[str, Any]] = None,
        cli: Optional[dict[str, Any]] = None,
        approval: Optional[dict[str, Any]] = None,
        observation_ref: Optional[str] = None,
        before_ref: Optional[str] = None,
        after_ref: Optional[str] = None,
        verification: Optional[dict[str, Any]] = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Append one audit entry and return the written record."""
        entry: dict[str, Any] = {
            "timestamp": utc_now_iso(),
            "sessionId": self.session_id,
            "taskId": self.task_id,
            "agent": agent,
            "role": role,
            "event": event,
        }
        if action is not None:
            entry["action"] = action
        if result is not None:
            entry["result"] = result
        if cli is not None:
            entry["cli"] = cli
        if approval is not None:
            entry["approval"] = approval
        if observation_ref is not None:
            entry["observationRef"] = observation_ref
        if before_ref is not None:
            entry["beforeObservationRef"] = before_ref
        if after_ref is not None:
            entry["afterObservationRef"] = after_ref
        if verification is not None:
            entry["verification"] = verification
        if extra:
            entry.update(extra)

        if self.redact_secrets:
            entry = _redact_obj(entry)

        line = json.dumps(entry, ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return entry

    def read_all(self) -> list[dict[str, Any]]:
        """Read every entry back (for replay / UI timeline / tests)."""
        if not self.path.exists():
            return []
        out: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
        return out
