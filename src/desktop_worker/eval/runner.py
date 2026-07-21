"""Evaluation runner (Phase 10).

Runs a suite of :class:`~desktop_worker.eval.spec.EvalTask` through the SAME
``AgentBridge`` an external MCP agent would use, so what is measured is what
agents actually experience.

Invariants this runner is built around
--------------------------------------
* **Per-task reset before AND after every trial.** WindowsAgentArena V1 lacked
  state reset between tasks, so mutations leaked across episodes and scores drifted.
  Reset runs on both sides so a trial is protected from its predecessor *and*
  leaves the desktop clean for its successor.
* **Per-trial crash isolation.** One exploding task must not abort the run;
  it is recorded as a failure with its error and the suite continues.
* **Emergency stop is honored.** If estop is engaged the run halts — the harness
  is not an exception to the safety model.
* **Round-trips are counted**, because model round-trips are 87-97% of end-to-end
  agent latency (OSWorld-Human, MLSys 2026); bridge calls are the thing an agent
  actually pays for, so they are the unit worth optimising.
* **The runner never mutates the system under test.** It observes only.
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

from desktop_worker.eval.spec import EvalResult, EvalTask, SuiteResult, TaskSummary
from desktop_worker.util import utc_now_iso


class CountingBridge:
    """Transparent proxy that counts calls to the wrapped bridge.

    A round-trip is one bridge method call: exactly what an MCP agent spends a
    model turn on. Counting here (rather than inside the bridge) keeps the
    system under test unmodified.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.calls: list[str] = []

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if not callable(attr):
            return attr

        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            self.calls.append(name)
            return attr(*args, **kwargs)

        return _wrapped

    @property
    def round_trips(self) -> int:
        return len(self.calls)

    def reset_count(self) -> None:
        self.calls.clear()


@dataclass
class EvalContext:
    """What a probe or oracle is handed."""

    bridge: Any
    task: EvalTask
    trial: int
    artifacts_dir: Optional[Any] = None
    scratch: dict[str, Any] = field(default_factory=dict)

    def observation_signature(self, *, screenshot: bool = False) -> str:
        """A cheap, stable signature of the current screen state.

        Used by :class:`~desktop_worker.eval.oracles.StateChanged` to detect
        silent no-ops. Deliberately coarse: active window + element count + the
        first elements' text, which changes when the UI meaningfully changes but
        not on cursor jitter.
        """
        obs = self.bridge.perceive(screenshot=screenshot) or {}
        window = obs.get("activeWindow") or {}
        elements = obs.get("elements") or []
        head = "|".join(str(e.get("text") or e.get("label") or "") for e in elements[:12])
        return f"{window.get('title', '')}#{len(elements)}#{head}"


class EvalRunner:
    """Runs tasks and aggregates results."""

    def __init__(
        self,
        bridge: Any,
        *,
        stop_checker: Optional[Callable[[], bool]] = None,
        on_event: Optional[Callable[[str, dict[str, Any]], None]] = None,
        artifacts_dir: Optional[Any] = None,
    ) -> None:
        self._raw_bridge = bridge
        self.bridge = CountingBridge(bridge)
        self._stop_checker = stop_checker
        self._on_event = on_event or (lambda _e, _d: None)
        self.artifacts_dir = artifacts_dir

    # -- internals ---------------------------------------------------------

    def _stopped(self) -> bool:
        if self._stop_checker is not None:
            return bool(self._stop_checker())
        status = getattr(self._raw_bridge, "status", None)
        if callable(status):
            try:
                return bool((status() or {}).get("stopped"))
            except Exception:
                return False
        return False

    def _run_actions(self, actions: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for action in actions:
            out.append(self.bridge.act(dict(action)))
        return out

    def _safe_reset(self, task: EvalTask, phase: str) -> Optional[str]:
        """Run reset actions, swallowing failures into a reported note.

        A failing reset must not be silently ignored (the next trial would run on
        dirty state and the result would be a lie), so it is surfaced — but it
        also must not crash the run.
        """
        if not task.reset:
            return None
        try:
            self._run_actions(task.reset)
            return None
        except Exception as exc:
            note = f"{phase}-reset failed: {exc}"
            self._on_event("reset_failed", {"task": task.id, "phase": phase, "error": str(exc)})
            return note

    # -- one trial ---------------------------------------------------------

    def run_trial(self, task: EvalTask, trial: int) -> EvalResult:
        self.bridge.reset_count()
        started = time.perf_counter()
        steps = 0
        notes: list[str] = []

        pre_note = self._safe_reset(task, "pre")
        if pre_note:
            notes.append(pre_note)

        try:
            if task.setup:
                # A failed setup invalidates the measurement: the trial would go on
                # to measure whatever state the desktop happened to be in. An earlier
                # version ignored setup results, and a malformed `tool.run` action was
                # rejected silently — so every app task measured the previously focused
                # window instead. Setup failure must abort the trial, loudly.
                setup_results = self._run_actions(task.setup)
                failed = [r for r in setup_results if not r.get("ok")]
                if failed:
                    raise RuntimeError(
                        "setup failed: "
                        + "; ".join(str(r.get("error") or r)[:160] for r in failed)
                    )

            ctx = EvalContext(
                bridge=self.bridge,
                task=task,
                trial=trial,
                artifacts_dir=self.artifacts_dir,
            )

            if task.probe is not None:
                payload = task.probe(ctx) or {}
                steps = int(payload.get("steps", 0)) or steps
            else:
                results = self._run_actions(task.actions[: task.max_steps])
                steps = len(results)
                payload = {
                    "ok": all(r.get("ok") for r in results) if results else False,
                    "results": results,
                }

            verdict = task.oracle.check(ctx, payload)
            passed, reason, detail = verdict.passed, verdict.reason, verdict.detail
            error = None

        except Exception as exc:  # per-trial isolation
            passed = False
            reason = f"trial raised {type(exc).__name__}: {exc}"
            detail = {"traceback": traceback.format_exc(limit=6)}
            error = str(exc)
            self._on_event("trial_error", {"task": task.id, "trial": trial, "error": str(exc)})

        finally:
            post_note = self._safe_reset(task, "post")
            if post_note:
                notes.append(post_note)

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if notes:
            detail = {**detail, "resetNotes": notes}

        return EvalResult(
            task_id=task.id,
            trial=trial,
            passed=passed,
            reason=reason,
            steps=steps,
            wall_clock_ms=elapsed_ms,
            round_trips=self.bridge.round_trips,
            feasible=task.feasible,
            error=error,
            detail=detail,
        )

    # -- whole suite -------------------------------------------------------

    def run_suite(
        self,
        tasks: Iterable[EvalTask],
        *,
        trials: int = 3,
        label: str = "run",
        tier: str = "a1",
    ) -> SuiteResult:
        if trials < 1:
            raise ValueError("trials must be >= 1")

        tasks = list(tasks)
        suite = SuiteResult(label=label, tier=tier, trials=trials, started_at=utc_now_iso())

        for task in tasks:
            if self._stopped():
                suite.notes["halted"] = f"emergency stop engaged before task {task.id}"
                self._on_event("halted", {"task": task.id})
                break

            summary = TaskSummary(
                task_id=task.id,
                tier=task.tier,
                app=task.app,
                feasible=task.feasible,
                trials=0,
                passes=0,
            )

            for trial in range(1, trials + 1):
                if self._stopped():
                    suite.notes["halted"] = f"emergency stop engaged during task {task.id}"
                    break

                result = self.run_trial(task, trial)
                suite.results.append(result)

                summary.trials += 1
                summary.passes += 1 if result.passed else 0
                summary.wall_clock_ms.append(result.wall_clock_ms)
                summary.steps.append(result.steps)
                summary.round_trips.append(result.round_trips)
                if not result.passed and result.reason not in summary.reasons:
                    summary.reasons.append(result.reason)

                self._on_event("trial_done", result.to_dict())

            if summary.trials:
                suite.summaries.append(summary)

        suite.finished_at = utc_now_iso()
        return suite
