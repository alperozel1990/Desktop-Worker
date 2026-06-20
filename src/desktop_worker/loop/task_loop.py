"""The observe-plan-act-verify-log loop (requirements sections 1, 14, 15).

This is the spine of Desktop-Worker. A pluggable :class:`Planner` decides the
next step from the current observation; the loop executes it, verifies the
result, logs everything, and continues until done, halted, or limits are hit.

The planner is an interface so an AI planner (Claude) can be dropped in later
without changing the loop. Phase 2 ships a :class:`ScriptedPlanner` that replays
a fixed list of steps — enough to prove the loop end-to-end and to test it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

from desktop_worker.actions.executor import ActionExecutor
from desktop_worker.audit.log import AuditLog
from desktop_worker.config import Limits
from desktop_worker.observation.observer import Observer
from desktop_worker.safety.emergency_stop import EmergencyStop, EmergencyStopError
from desktop_worker.schema.actions import Action, parse_action
from desktop_worker.schema.observations import Observation
from desktop_worker.schema.results import ActionResult, VerificationResult
from desktop_worker.util import utc_now_iso


@dataclass
class PlannedStep:
    """One step the planner proposes."""

    action: Action
    description: str = ""
    expected: dict[str, Any] = field(default_factory=dict)  # verification spec


class Planner(Protocol):
    """Decides the next step (or None when the task is complete)."""

    def next_step(self, observation: Observation, history: list[ActionResult]) -> Optional[PlannedStep]:
        ...


class _PerceiverLike(Protocol):
    """Anything that can enrich an observation with structured elements."""

    def perceive(self, observation: Observation) -> Observation:
        ...


class ScriptedPlanner:
    """Replays a fixed list of steps. Used for tests and the demo task."""

    def __init__(self, steps: list[PlannedStep]) -> None:
        self._steps = list(steps)
        self._i = 0

    def next_step(self, observation, history) -> Optional[PlannedStep]:
        if self._i >= len(self._steps):
            return None
        step = self._steps[self._i]
        self._i += 1
        return step

    @classmethod
    def from_dicts(cls, raw: list[dict[str, Any]]) -> "ScriptedPlanner":
        """Build from a list of {action, description?, expectedResult?} dicts."""
        steps: list[PlannedStep] = []
        for item in raw:
            action = parse_action(item["action"])
            steps.append(PlannedStep(
                action=action,
                description=item.get("description", action.summary),
                expected=item.get("expectedResult", {}),
            ))
        return cls(steps)


@dataclass
class TaskReport:
    """Final task report (requirements sections 3, 17)."""

    task_id: str
    startedAt: str
    endedAt: str
    completed: bool
    halted: bool
    steps_run: int
    successes: int
    failures: int
    stop_reason: str = ""
    step_records: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "taskId": self.task_id,
            "startedAt": self.startedAt,
            "endedAt": self.endedAt,
            "completed": self.completed,
            "halted": self.halted,
            "stepsRun": self.steps_run,
            "successes": self.successes,
            "failures": self.failures,
            "stopReason": self.stop_reason,
            "steps": self.step_records,
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Task Report - {self.task_id}",
            "",
            f"- Started: {self.startedAt}",
            f"- Ended: {self.endedAt}",
            f"- Completed: {self.completed}",
            f"- Halted: {self.halted}",
            f"- Steps run: {self.steps_run} ({self.successes} ok, {self.failures} failed)",
        ]
        if self.stop_reason:
            lines.append(f"- Stop reason: {self.stop_reason}")
        lines += ["", "## Steps", ""]
        for i, rec in enumerate(self.step_records, 1):
            ok = "OK" if rec.get("success") else "FAIL"
            lines.append(f"{i}. [{ok}] {rec.get('description', rec.get('action'))}")
        return "\n".join(lines) + "\n"


class TaskLoop:
    """Runs the observe-plan-act-verify-log loop for a single task."""

    def __init__(
        self,
        *,
        task_id: str,
        planner: Planner,
        observer: Observer,
        executor: ActionExecutor,
        audit: AuditLog,
        estop: EmergencyStop,
        limits: Optional[Limits] = None,
        now: Optional[Callable[[], float]] = None,
        perceiver: Optional["_PerceiverLike"] = None,
    ) -> None:
        self.task_id = task_id
        self.planner = planner
        self.observer = observer
        self.executor = executor
        self.audit = audit
        self.estop = estop
        self.limits = limits or Limits()
        # Injectable monotonic clock (seconds) so the time limit is testable.
        self._now = now or time.monotonic
        # Optional perception (DW-PERCEPTION-WIRE). When set, observations are
        # enriched with structured elements (UIA-preferred, OCR fallback) so the
        # AI/audit see attributable elements, not just raw coordinates. Off by
        # default — no perception dependency is forced on the loop.
        self.perceiver = perceiver

    def _observe(self, label: str):
        """Capture an observation, enriching it with elements if a perceiver is set."""
        obs = self.observer.observe(label)
        if self.perceiver is not None:
            obs = self.perceiver.perceive(obs)
        return obs

    # Action families that are safe to re-execute on failure without
    # accumulating side effects (requirements §15 "retry safe actions").
    # Excluded (NOT retried): keyboard.type (would duplicate text), mouse.drag
    # (partial drag), mouse.down/up (unbalanced), cli.run (side effects).
    # NOTE: only action types the executor can actually dispatch are listed.
    # window.focus and verify are handled by higher layers (not the executor)
    # today, so retrying them would just fail repeatedly — they are excluded
    # until a higher layer executes them.
    _RETRYABLE = frozenset({
        "mouse.move", "mouse.moveRelative", "mouse.click", "mouse.doubleClick",
        "mouse.rightClick", "mouse.scroll", "keyboard.press", "keyboard.hotkey",
        "clipboard.set", "clipboard.get", "wait",
    })

    def _is_retryable(self, action: Action) -> bool:
        return action.type in self._RETRYABLE

    def _try_replan(
        self, failed: PlannedStep, observation: Observation, history: list[ActionResult]
    ) -> Optional[PlannedStep]:
        """Ask the planner for a revised step, if it supports re-planning.

        Planners may optionally implement ``replan(failed_step, observation,
        history) -> Optional[PlannedStep]``. Planners without it (e.g. the
        ScriptedPlanner) simply cannot re-plan, so the loop safe-stops.
        """
        replan = getattr(self.planner, "replan", None)
        if callable(replan):
            return replan(failed, observation, history)
        return None

    def run(self) -> TaskReport:
        started = utc_now_iso()
        history: list[ActionResult] = []
        records: list[dict[str, Any]] = []
        successes = failures = 0
        completed = halted = False
        stop_reason = ""

        self.audit.record("task.started", event_task=self.task_id)
        start_mono = self._now()

        while True:
            # Action-count limit (requirements section 12).
            if len(records) >= self.limits.max_actions_per_task:
                stop_reason = f"reached max actions ({self.limits.max_actions_per_task})"
                break

            # Time limit (requirements section 12).
            if self._now() - start_mono >= self.limits.max_task_seconds:
                stop_reason = f"reached max task time ({self.limits.max_task_seconds}s)"
                self.audit.record("task.timeout", reason=stop_reason)
                break

            # Emergency stop guard.
            try:
                self.estop.check()
            except EmergencyStopError as exc:
                halted = True
                stop_reason = f"emergency stop: {exc}"
                self.audit.record("task.halted", reason=stop_reason)
                break

            # OBSERVE (before) — enriched with perception elements if available.
            before = self._observe("before")

            # PLAN.
            step = self.planner.next_step(before, history)
            if step is None:
                completed = True
                break

            self.audit.record(
                "step.planned",
                planned={"description": step.description,
                         "action": step.action.to_dict(),
                         "expected": step.expected},
                before_ref=before.screenshotRef,
                elements=[e.to_dict() for e in before.elements],
            )

            # ACT → VERIFY with recovery: retry safe actions up to max_retries,
            # then ask the planner to re-plan, then safe-stop (requirements §15).
            attempts = 0
            replans = 0
            time_exceeded = False
            while True:
                result = self.executor.execute(step.action)
                after = self._observe("after")
                verification = self._verify(step, after, result)
                ok = result.success and (verification is None or verification.passed)
                if ok:
                    break

                # Time guard inside recovery: do not spend further retries/replans
                # once the task wall-clock limit is reached (requirements §12).
                if self._now() - start_mono >= self.limits.max_task_seconds:
                    time_exceeded = True
                    break

                # Retry the same (safe) action after re-observing.
                if self._is_retryable(step.action) and attempts < self.limits.max_retries:
                    attempts += 1
                    self.audit.record(
                        "step.retry",
                        result=result.to_dict(),
                        verification=verification.to_dict() if verification else None,
                        retry={"attempt": attempts, "max": self.limits.max_retries},
                    )
                    continue

                # Retries exhausted or action unsafe to retry: try a revised plan.
                # Check the bound BEFORE asking the planner so we never make an
                # extra (potentially expensive AI) re-plan call past the limit.
                if replans < self.limits.max_retries:
                    revised = self._try_replan(step, after, history)
                    if revised is not None:
                        replans += 1
                        self.audit.record(
                            "step.replanned",
                            planned={"description": revised.description,
                                     "action": revised.action.to_dict(),
                                     "expected": revised.expected},
                        )
                        step = revised
                        attempts = 0
                        continue

                break  # give up — safe-stop handled below

            result.retries = attempts
            history.append(result)
            successes += int(ok)
            failures += int(not ok)

            self.audit.record(
                "step.completed",
                result=result.to_dict(),
                verification=verification.to_dict() if verification else None,
                after_ref=after.screenshotRef,
            )

            records.append({
                "description": step.description,
                "action": str(step.action),
                "success": ok,
                "retries": attempts,
                "error": result.error,
                "verificationPassed": verification.passed if verification else None,
            })

            if not ok:
                if time_exceeded:
                    stop_reason = f"reached max task time ({self.limits.max_task_seconds}s) during step"
                    self.audit.record("task.timeout", reason=stop_reason)
                elif not result.success:
                    stop_reason = f"step failed after {attempts} retr{'y' if attempts == 1 else 'ies'}: {result.error}"
                else:
                    stop_reason = f"verification failed after {attempts} retr{'y' if attempts == 1 else 'ies'}"
                break

        ended = utc_now_iso()
        report = TaskReport(
            task_id=self.task_id, startedAt=started, endedAt=ended,
            completed=completed, halted=halted, steps_run=len(records),
            successes=successes, failures=failures, stop_reason=stop_reason,
            step_records=records,
        )
        self.audit.record("task.finished", result=report.to_dict())
        return report

    def _verify(
        self, step: PlannedStep, after: Observation, result: ActionResult
    ) -> Optional[VerificationResult]:
        """Minimal verification using structured observation (section 14).

        Richer verification (OCR text match, UIA element state) arrives with the
        Perception layer in Phase 4. Here we check the post-conditions we can
        evaluate from a structured observation plus the action result.
        """
        expected = step.expected or {}
        if not expected:
            return None

        if "activeWindowContains" in expected:
            want = expected["activeWindowContains"]
            title = after.activeWindow.title if after.activeWindow else ""
            passed = want.lower() in title.lower()
            return VerificationResult(
                passed=passed, method="activeWindow",
                expected={"activeWindowContains": want},
                observed={"activeWindow": title},
            )

        if "clipboardEquals" in expected:
            got = result.detail.get("text", "")
            passed = got == expected["clipboardEquals"]
            return VerificationResult(
                passed=passed, method="clipboard",
                expected={"clipboardEquals": expected["clipboardEquals"]},
                observed={"text": got},
            )

        # Unknown expectation kinds (e.g. visibleTextContains) need perception;
        # mark as not-yet-verifiable rather than silently passing.
        return VerificationResult(
            passed=False, method="unsupported",
            expected=expected, observed={},
            note="verification method requires the Perception layer (Phase 4)",
        )
