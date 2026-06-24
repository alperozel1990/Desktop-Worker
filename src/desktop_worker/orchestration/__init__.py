"""Multi-agent orchestration (requirements Phase 6).

Formalizes the four roles the project already operates by — Strategist,
Implementer, Codex Auditor, Northstar Auditor — as composable, dependency-injected
units plus a deterministic coordinator state machine. Claude-driven roles route
through the audited CLI broker (no API key, no raw subprocess) and every role
output is validated against the handoff schema before use, so a malformed model
response can never drive execution.

The schema (AgentTask / AgentReport / AuditorFinding) follows the same
dataclass + camelCase ``to_dict()`` + standalone ``parse_*`` style as
``schema/actions.py``; the audit log already carries ``agent``/``role`` fields,
so no audit-schema change is needed to attribute orchestration actors.
"""

from desktop_worker.orchestration.schema import (
    AgentReport,
    AgentTask,
    AuditorFinding,
    OrchestrationValidationError,
    parse_agent_report,
    parse_agent_task,
    parse_finding,
)

__all__ = [
    "AgentTask", "AgentReport", "AuditorFinding", "OrchestrationValidationError",
    "parse_agent_task", "parse_agent_report", "parse_finding",
]
