"""Orchestration roles: Strategist / Implementer / Codex + Northstar Auditor.

Each role wraps a Claude call (injected as ``ask``; default = a broker-routed
``claude`` bound to that role's audit attribution) and validates the model's
output against the handoff schema. A malformed or missing response fails safe:
the Strategist yields no tasks, the Implementer reports ``failed``, and an
auditor returns a non-approving verdict (deny-by-default).

All Claude calls are INJECTED, so every role is unit-testable with plain lambdas
and no broker/desktop.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from desktop_worker.orchestration.claude_io import load_json, make_role_ask
from desktop_worker.orchestration.schema import (
    AgentReport,
    AgentTask,
    AuditorFinding,
    OrchestrationValidationError,
    parse_agent_report,
    parse_agent_task,
    parse_finding,
)

AskFn = Callable[[str], str]


class _Role:
    """Common wiring: an injected ``ask`` or a broker-routed default."""

    agent = "Role"
    role = "role"

    def __init__(self, *, ask: Optional[AskFn] = None, broker: Any = None,
                 cwd: str = ".", audit: Any = None) -> None:
        if ask is None:
            if broker is None:
                raise ValueError(f"{self.agent} needs either ask= or broker=")
            ask = make_role_ask(broker, cwd, agent=self.agent, role=self.role)
        self._ask: AskFn = ask
        self._audit = audit
        self.last_error: str = ""
        self.last_raw: str = ""

    def _call(self, prompt: str) -> Any:
        """Call Claude and parse JSON; records last_raw/last_error."""
        self.last_error = ""
        raw = self._ask(prompt)
        self.last_raw = raw or ""
        return load_json(raw)

    def _log(self, event: str, **fields: Any) -> None:
        if self._audit is not None:
            try:
                self._audit.record(event, agent=self.agent, role=self.role, **fields)
            except Exception:
                pass


class Strategist(_Role):
    """Decompose a high-level goal into scoped AgentTasks with acceptance criteria."""

    agent = "Strategist"
    role = "strategist"

    def plan(self, goal: str) -> list[AgentTask]:
        prompt = (
            "You are the Strategist for an autonomous desktop-automation agent. "
            f"Decompose this goal into a SHORT list of scoped, independently-verifiable "
            f"sub-tasks.\n\nGOAL: {goal}\n\n"
            "Reply with ONLY a JSON array. Each element: "
            '{"id": "T1", "goal": "...", "acceptance": ["..."], '
            '"constraints": ["..."], "forbiddenFiles": ["..."]}. '
            "Keep it to at most 6 tasks."
        )
        try:
            data = self._call(prompt)
        except Exception as exc:  # noqa: BLE001 — any failure -> no tasks (fail safe)
            self.last_error = str(exc)
            self._log("orch.strategist_failed", error=str(exc))
            return []
        if not isinstance(data, list):
            self.last_error = "strategist output was not a JSON array"
            self._log("orch.strategist_failed", error=self.last_error)
            return []
        tasks: list[AgentTask] = []
        for item in data:
            try:
                tasks.append(parse_agent_task(item))
            except OrchestrationValidationError as exc:
                self.last_error = str(exc)  # skip the bad task, keep the good ones
        self._log("orch.planned", taskCount=len(tasks))
        return tasks


class Implementer(_Role):
    """Carry out one AgentTask and return a structured AgentReport.

    By default the Implementer asks Claude for a structured report (plan-only,
    safe). A real desktop execution can be injected via ``execute_fn`` (wired by
    the coordinator only under an explicit --execute opt-in).
    """

    agent = "Implementer"
    role = "implementer"

    def __init__(self, *, execute_fn: Optional[Callable[[AgentTask], AgentReport]] = None,
                 **kw: Any) -> None:
        self._execute_fn = execute_fn
        # ask is optional when execute_fn is provided.
        if kw.get("ask") is None and kw.get("broker") is None and execute_fn is not None:
            kw["ask"] = lambda _p: "{}"
        super().__init__(**kw)

    def implement(self, task: AgentTask) -> AgentReport:
        if self._execute_fn is not None:
            try:
                return self._execute_fn(task)
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)
                return AgentReport(task_id=task.id, status="failed",
                                   summary=f"execution error: {exc}")
        prompt = (
            "You are the Implementer. For the task below, report what was/should be "
            "done.\n\nTASK:\n" + str(task.to_dict()) + "\n\n"
            'Reply with ONLY a JSON object: {"taskId": "' + task.id + '", '
            '"status": "done|blocked|failed", "summary": "...", '
            '"changes": ["..."], "evidence": ["..."]}.'
        )
        try:
            data = self._call(prompt)
            report = parse_agent_report(data)
        except Exception as exc:  # noqa: BLE001 — fail safe to a failed report
            self.last_error = str(exc)
            self._log("orch.implementer_failed", taskId=task.id, error=str(exc))
            return AgentReport(task_id=task.id, status="failed",
                               summary=f"implementer output invalid: {exc}")
        self._log("orch.implemented", taskId=task.id, status=report.status)
        return report


class _Auditor(_Role):
    """Shared auditor logic: review a (task, report) and return a finding."""

    lens = "correctness and project invariants"

    def review(self, task: AgentTask, report: AgentReport) -> AuditorFinding:
        prompt = (
            f"You are the {self.agent}. Judge the report for the task below on "
            f"{self.lens}.\n\nTASK:\n{task.to_dict()}\n\nREPORT:\n{report.to_dict()}\n\n"
            'Reply with ONLY a JSON object: {"severity": '
            '"info|low|medium|high|critical", "verdict": "approve|revise|block", '
            '"message": "...", "location": "..."}.'
        )
        try:
            data = self._call(prompt)
            finding = parse_finding(data)
        except Exception as exc:  # noqa: BLE001 — auditor fails CLOSED (never approve)
            self.last_error = str(exc)
            self._log("orch.auditor_failed", taskId=task.id, error=str(exc))
            return AuditorFinding(severity="high", verdict="block",
                                  message=f"{self.agent} output unparseable: {exc}",
                                  location=task.id)
        self._log("orch.reviewed", taskId=task.id, verdict=finding.verdict,
                  severity=finding.severity)
        return finding


class CodexAuditor(_Auditor):
    """Reviews code-level correctness, safety, and invariant compliance."""

    agent = "Codex Auditor"
    role = "codex_auditor"
    lens = "code correctness, safety invariants (broker-only CLI, estop, audit), and tests"


class NorthstarAuditor(_Auditor):
    """Reviews direction/alignment with the product north star."""

    agent = "Northstar Auditor"
    role = "northstar_auditor"
    lens = "alignment with the AI-control-ready north star and the loop (observe-plan-act-verify-log)"
