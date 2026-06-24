"""Coordinator: the multi-agent state machine (requirements Phase 6).

Deterministic orchestration over injected roles:

    Strategist.plan(goal)
        -> for each task: Implementer.implement(task)
            -> CodexAuditor.review + NorthstarAuditor.review
            -> accept (status done AND both approve)
             | blocked (any verdict block, or status failed)
             | revise  (otherwise)

Every transition is audited (agent="Coordinator"). The roles are injected, so the
state machine is pure and fully unit-testable with stub roles. Real desktop
execution only happens if the Implementer was given an ``execute_fn`` (a deliberate
--execute opt-in); by default the run is plan-only and side-effect-free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from desktop_worker.orchestration.schema import AgentReport, AgentTask, AuditorFinding


@dataclass
class TaskOutcome:
    task: AgentTask
    report: AgentReport
    codex: AuditorFinding
    northstar: AuditorFinding
    outcome: str  # "accepted" | "blocked" | "revise"

    def to_dict(self) -> dict[str, Any]:
        return {"task": self.task.to_dict(), "report": self.report.to_dict(),
                "codex": self.codex.to_dict(), "northstar": self.northstar.to_dict(),
                "outcome": self.outcome}


@dataclass
class CoordinationResult:
    goal: str
    outcomes: list[TaskOutcome] = field(default_factory=list)
    error: str = ""

    @property
    def accepted(self) -> int:
        return sum(1 for o in self.outcomes if o.outcome == "accepted")

    @property
    def blocked(self) -> int:
        return sum(1 for o in self.outcomes if o.outcome == "blocked")

    def to_dict(self) -> dict[str, Any]:
        return {"goal": self.goal, "taskCount": len(self.outcomes),
                "accepted": self.accepted, "blocked": self.blocked,
                "outcomes": [o.to_dict() for o in self.outcomes], "error": self.error}

    def to_markdown(self) -> str:
        lines = [f"# Orchestration: {self.goal}",
                 f"tasks={len(self.outcomes)} accepted={self.accepted} blocked={self.blocked}"]
        if self.error:
            lines.append(f"error: {self.error}")
        for o in self.outcomes:
            lines.append(f"- [{o.outcome}] {o.task.id}: {o.task.goal} "
                         f"(impl={o.report.status}, codex={o.codex.verdict}, "
                         f"northstar={o.northstar.verdict})")
        return "\n".join(lines)


class Coordinator:
    def __init__(self, *, strategist, implementer, codex, northstar, audit: Any = None) -> None:
        self._strategist = strategist
        self._implementer = implementer
        self._codex = codex
        self._northstar = northstar
        self._audit = audit

    def _log(self, event: str, **fields: Any) -> None:
        if self._audit is not None:
            try:
                self._audit.record(event, agent="Coordinator", role="coordinator", **fields)
            except Exception:
                pass

    @staticmethod
    def _classify(report: AgentReport, codex: AuditorFinding,
                  northstar: AuditorFinding) -> str:
        verdicts = (codex.verdict, northstar.verdict)
        # A never-completed task (failed/blocked/skipped) or any block verdict =>
        # blocked; it can never be "accepted" or endlessly "revise"d.
        if "block" in verdicts or report.status in ("failed", "blocked", "skipped"):
            return "blocked"
        if report.status == "done" and all(v == "approve" for v in verdicts):
            return "accepted"
        return "revise"

    def run(self, goal: str) -> CoordinationResult:
        self._log("orch.coordinator_start", goal=goal)
        tasks = self._strategist.plan(goal)
        if not tasks:
            err = getattr(self._strategist, "last_error", "") or "no tasks produced"
            self._log("orch.coordinator_done", goal=goal, taskCount=0, error=err)
            return CoordinationResult(goal=goal, error=err)

        outcomes: list[TaskOutcome] = []
        for task in tasks:
            report = self._implementer.implement(task)
            codex = self._codex.review(task, report)
            northstar = self._northstar.review(task, report)
            outcome = self._classify(report, codex, northstar)
            self._log("orch.task_outcome", taskId=task.id, outcome=outcome,
                      implStatus=report.status, codex=codex.verdict,
                      northstar=northstar.verdict)
            outcomes.append(TaskOutcome(task, report, codex, northstar, outcome))

        result = CoordinationResult(goal=goal, outcomes=outcomes)
        self._log("orch.coordinator_done", goal=goal, taskCount=len(outcomes),
                  accepted=result.accepted, blocked=result.blocked)
        return result
