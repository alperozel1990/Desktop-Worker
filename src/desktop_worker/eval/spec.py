"""Evaluation task/result data model (Phase 10).

Pure, dependency-free and serializable — the measurement vocabulary. Nothing here
touches the desktop; the runner does that.

Design notes
------------
* A task is EITHER a list of structured ``actions`` (executed through the same
  bridge an external AI would use) OR a ``probe`` callable for capability checks
  that are not expressible as actions (e.g. "call perceive twice and compare
  element ids"). Probes are how Tier A2 grades the tool surface.
* ``feasible`` exists to defeat "infeasible hacking" (WindowsAgentArena-V2): a
  task that CANNOT be completed is scored on a separate axis, where success means
  the agent correctly reported impossibility rather than fabricating a result.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# Tier A1: Null backends, CI, zero Claude quota.
# Tier A2: live apps, deterministic, zero Claude quota — grades the tool surface.
# Tier B : full AI task runs — SPENDS CLAUDE QUOTA, opt-in only.
TIERS: tuple[str, ...] = ("a1", "a2", "b")


@dataclass(frozen=True)
class EvalTask:
    """One evaluation task.

    ``setup``/``reset`` are structured actions run before/after each trial so that
    trials cannot leak state into one another (WindowsAgentArena V1's defect).
    """

    id: str
    description: str
    tier: str
    app: str = "none"
    feasible: bool = True
    actions: tuple[dict[str, Any], ...] = ()
    probe: Optional[Callable[[Any], dict[str, Any]]] = None
    oracle: Any = None
    setup: tuple[dict[str, Any], ...] = ()
    reset: tuple[dict[str, Any], ...] = ()
    max_steps: int = 20
    tags: tuple[str, ...] = ()
    # Free-text pointer to the real failure or acceptance criterion this task came
    # from. Kept mandatory-by-convention so the suite cannot drift into invention.
    seeded_from: str = ""

    def __post_init__(self) -> None:
        if self.tier not in TIERS:
            raise ValueError(f"unknown tier {self.tier!r}; expected one of {TIERS}")
        if not self.id:
            raise ValueError("EvalTask.id must be non-empty")
        if self.probe is None and not self.actions:
            raise ValueError(f"task {self.id!r} has neither actions nor a probe")
        if self.oracle is None:
            raise ValueError(f"task {self.id!r} has no oracle — unscoreable")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "tier": self.tier,
            "app": self.app,
            "feasible": self.feasible,
            "actionCount": len(self.actions),
            "hasProbe": self.probe is not None,
            "oracle": getattr(self.oracle, "name", type(self.oracle).__name__),
            "maxSteps": self.max_steps,
            "tags": list(self.tags),
            "seededFrom": self.seeded_from,
        }


@dataclass(frozen=True)
class EvalResult:
    """Outcome of ONE trial of one task."""

    task_id: str
    trial: int
    passed: bool
    reason: str
    steps: int = 0
    wall_clock_ms: float = 0.0
    round_trips: int = 0
    feasible: bool = True
    error: Optional[str] = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "taskId": self.task_id,
            "trial": self.trial,
            "passed": self.passed,
            "reason": self.reason,
            "steps": self.steps,
            "wallClockMs": round(self.wall_clock_ms, 2),
            "roundTrips": self.round_trips,
            "feasible": self.feasible,
            "error": self.error,
            "detail": self.detail,
        }


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Used instead of a bare success rate because a 20-50 task suite has wide
    confidence intervals; reporting a point estimate alone invites reading noise
    as signal (Miller 2024, arXiv 2411.00640).
    """
    if total <= 0:
        return (0.0, 0.0)
    p = successes / total
    denom = 1.0 + (z * z) / total
    centre = p + (z * z) / (2 * total)
    margin = z * math.sqrt((p * (1 - p) + (z * z) / (4 * total)) / total)
    low = (centre - margin) / denom
    high = (centre + margin) / denom
    return (max(0.0, low), min(1.0, high))


@dataclass
class TaskSummary:
    """Aggregate across the trials of ONE task."""

    task_id: str
    tier: str
    app: str
    feasible: bool
    trials: int
    passes: int
    reasons: list[str] = field(default_factory=list)
    wall_clock_ms: list[float] = field(default_factory=list)
    steps: list[int] = field(default_factory=list)
    round_trips: list[int] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return self.passes / self.trials if self.trials else 0.0

    @property
    def flaky(self) -> bool:
        """True when trials disagree — the single most useful debugging signal."""
        return 0 < self.passes < self.trials

    def to_dict(self) -> dict[str, Any]:
        low, high = wilson_interval(self.passes, self.trials)
        return {
            "taskId": self.task_id,
            "tier": self.tier,
            "app": self.app,
            "feasible": self.feasible,
            "trials": self.trials,
            "passes": self.passes,
            "successRate": round(self.success_rate, 4),
            "ci95": [round(low, 4), round(high, 4)],
            "flaky": self.flaky,
            "meanWallClockMs": round(statistics.fmean(self.wall_clock_ms), 2)
            if self.wall_clock_ms
            else 0.0,
            "meanSteps": round(statistics.fmean(self.steps), 2) if self.steps else 0.0,
            "meanRoundTrips": round(statistics.fmean(self.round_trips), 2)
            if self.round_trips
            else 0.0,
            "reasons": self.reasons,
        }


@dataclass
class SuiteResult:
    """Aggregate across every task in a run — the artifact you diff before/after."""

    label: str
    tier: str
    trials: int
    summaries: list[TaskSummary] = field(default_factory=list)
    results: list[EvalResult] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    notes: dict[str, Any] = field(default_factory=dict)

    # Feasible and infeasible tasks are scored on SEPARATE axes so a model cannot
    # inflate its headline number by "succeeding" at impossible tasks.
    def _split(self) -> tuple[list[TaskSummary], list[TaskSummary]]:
        feasible = [s for s in self.summaries if s.feasible]
        infeasible = [s for s in self.summaries if not s.feasible]
        return feasible, infeasible

    def _rate(self, summaries: list[TaskSummary]) -> dict[str, Any]:
        passes = sum(s.passes for s in summaries)
        total = sum(s.trials for s in summaries)
        low, high = wilson_interval(passes, total)
        return {
            "tasks": len(summaries),
            "trials": total,
            "passes": passes,
            "successRate": round(passes / total, 4) if total else 0.0,
            "ci95": [round(low, 4), round(high, 4)],
        }

    def to_dict(self) -> dict[str, Any]:
        feasible, infeasible = self._split()
        all_rt = [rt for s in self.summaries for rt in s.round_trips]
        all_wc = [wc for s in self.summaries for wc in s.wall_clock_ms]
        return {
            "label": self.label,
            "tier": self.tier,
            "trialsPerTask": self.trials,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "feasible": self._rate(feasible),
            "infeasible": self._rate(infeasible),
            "flakyTasks": [s.task_id for s in self.summaries if s.flaky],
            "totalRoundTrips": sum(all_rt),
            "meanRoundTripsPerTrial": round(statistics.fmean(all_rt), 2) if all_rt else 0.0,
            "meanWallClockMsPerTrial": round(statistics.fmean(all_wc), 2) if all_wc else 0.0,
            "tasks": [s.to_dict() for s in self.summaries],
            "notes": self.notes,
        }
