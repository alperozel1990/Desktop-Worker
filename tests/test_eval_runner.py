"""Tests for the eval runner and spec (Phase 10).

The runner's value is entirely in its invariants: reset on both sides of every
trial, crash isolation, estop obedience, honest round-trip counting, and keeping
feasible/infeasible on separate axes. Each is pinned here.
"""

import pytest

from desktop_worker.eval.oracles import ProbeFlag, Verdict
from desktop_worker.eval.runner import CountingBridge, EvalRunner
from desktop_worker.eval.spec import EvalTask, SuiteResult, TaskSummary, wilson_interval


class RecordingBridge:
    """Records every call so tests can assert on ordering and counts."""

    def __init__(self, *, stopped=False, fail_on=None):
        self.calls = []
        self._stopped = stopped
        self._fail_on = fail_on or set()

    def act(self, action):
        self.calls.append(("act", action.get("type")))
        if action.get("type") in self._fail_on:
            raise RuntimeError(f"action {action.get('type')} exploded")
        return {"ok": True, "actionType": action.get("type")}

    def perceive(self, screenshot=True):
        self.calls.append(("perceive", screenshot))
        return {"ok": True, "elements": [], "activeWindow": {"title": "T"}}

    def status(self):
        return {"ok": True, "stopped": self._stopped}


class PassOracle:
    name = "always_pass"

    def check(self, ctx, payload):
        return Verdict(True, "ok", {})


class FailOracle:
    name = "always_fail"

    def check(self, ctx, payload):
        return Verdict(False, "nope", {})


def _task(**kw):
    base = dict(
        id="T1",
        description="d",
        tier="a1",
        probe=lambda ctx: {"flag": True, "steps": 1},
        oracle=ProbeFlag("flag"),
    )
    base.update(kw)
    return EvalTask(**base)


# -- spec validation -------------------------------------------------------


def test_task_rejects_unknown_tier():
    with pytest.raises(ValueError, match="unknown tier"):
        _task(tier="z")


def test_task_requires_an_oracle():
    with pytest.raises(ValueError, match="no oracle"):
        EvalTask(id="X", description="d", tier="a1", probe=lambda c: {}, oracle=None)


def test_task_requires_actions_or_probe():
    with pytest.raises(ValueError, match="neither actions nor a probe"):
        EvalTask(id="X", description="d", tier="a1", oracle=PassOracle())


# -- Wilson interval -------------------------------------------------------


def test_wilson_interval_is_wide_for_small_samples():
    """The whole point: 3/3 must NOT read as certainty."""
    low, high = wilson_interval(3, 3)
    assert low < 0.5
    assert high == pytest.approx(1.0, abs=0.01)


def test_wilson_interval_narrows_as_n_grows():
    narrow = wilson_interval(90, 100)
    wide = wilson_interval(9, 10)
    assert (narrow[1] - narrow[0]) < (wide[1] - wide[0])


def test_wilson_interval_handles_zero_total():
    assert wilson_interval(0, 0) == (0.0, 0.0)


# -- CountingBridge --------------------------------------------------------


def test_counting_bridge_counts_calls_and_passes_through():
    inner = RecordingBridge()
    counting = CountingBridge(inner)

    assert counting.act({"type": "mouse.move"})["ok"] is True
    counting.perceive(screenshot=False)
    assert counting.round_trips == 2

    counting.reset_count()
    assert counting.round_trips == 0


# -- reset discipline ------------------------------------------------------


def test_reset_runs_before_and_after_every_trial():
    """Both sides: protects this trial from the last, and the next from this one."""
    bridge = RecordingBridge()
    task = _task(reset=({"type": "reset.marker"},))
    runner = EvalRunner(bridge)

    runner.run_trial(task, 1)

    resets = [c for c in bridge.calls if c == ("act", "reset.marker")]
    assert len(resets) == 2, f"expected pre+post reset, got {bridge.calls}"
    assert bridge.calls[0] == ("act", "reset.marker")
    assert bridge.calls[-1] == ("act", "reset.marker")


def test_failing_reset_is_surfaced_not_swallowed():
    """A silent reset failure would make every later result a lie."""
    bridge = RecordingBridge(fail_on={"reset.marker"})
    task = _task(reset=({"type": "reset.marker"},))

    result = EvalRunner(bridge).run_trial(task, 1)

    notes = result.detail.get("resetNotes") or []
    assert any("reset failed" in n for n in notes), result.detail
    # the trial itself still produced a verdict rather than crashing the run
    assert result.passed is True


def test_post_reset_runs_even_when_the_trial_raises():
    bridge = RecordingBridge()

    def boom(ctx):
        raise RuntimeError("probe exploded")

    task = _task(probe=boom, reset=({"type": "reset.marker"},))
    result = EvalRunner(bridge).run_trial(task, 1)

    assert result.passed is False
    assert bridge.calls[-1] == ("act", "reset.marker")


# -- crash isolation -------------------------------------------------------


def test_trial_exception_is_recorded_not_raised():
    def boom(ctx):
        raise ValueError("kaboom")

    result = EvalRunner(RecordingBridge()).run_trial(_task(probe=boom), 1)

    assert result.passed is False
    assert result.error == "kaboom"
    assert "ValueError" in result.reason
    assert "traceback" in result.detail


def test_one_exploding_task_does_not_abort_the_suite():
    def boom(ctx):
        raise RuntimeError("bad")

    tasks = [
        _task(id="GOOD-1"),
        _task(id="BOOM", probe=boom),
        _task(id="GOOD-2"),
    ]
    suite = EvalRunner(RecordingBridge()).run_suite(tasks, trials=1)

    assert [s.task_id for s in suite.summaries] == ["GOOD-1", "BOOM", "GOOD-2"]
    assert suite.summaries[1].passes == 0
    assert suite.summaries[2].passes == 1


# -- emergency stop --------------------------------------------------------


def test_suite_halts_when_emergency_stop_is_engaged():
    """The harness is not exempt from the safety model."""
    bridge = RecordingBridge(stopped=True)
    suite = EvalRunner(bridge).run_suite([_task(id="T1"), _task(id="T2")], trials=1)

    assert suite.summaries == []
    assert "halted" in suite.notes


def test_explicit_stop_checker_overrides_bridge_status():
    """The runner checks before each task AND before each trial, so a task that
    completes consumes two checks; stopping on the third halts at task 2."""
    calls = {"n": 0}

    def stop_after_first_task():
        calls["n"] += 1
        return calls["n"] > 2

    suite = EvalRunner(RecordingBridge(), stop_checker=stop_after_first_task).run_suite(
        [_task(id="T1"), _task(id="T2")], trials=1
    )
    assert [s.task_id for s in suite.summaries] == ["T1"]
    assert "halted" in suite.notes


# -- metrics ---------------------------------------------------------------


def test_round_trips_are_counted_per_trial_not_cumulatively():
    bridge = RecordingBridge()
    task = _task(actions=({"type": "a"}, {"type": "b"}), probe=None, oracle=PassOracle())
    runner = EvalRunner(bridge)

    first = runner.run_trial(task, 1)
    second = runner.run_trial(task, 2)

    assert first.round_trips == 2
    assert second.round_trips == 2, "counter must reset between trials"


def test_wall_clock_is_recorded():
    result = EvalRunner(RecordingBridge()).run_trial(_task(), 1)
    assert result.wall_clock_ms >= 0.0


def test_max_steps_caps_executed_actions():
    bridge = RecordingBridge()
    task = _task(
        actions=tuple({"type": f"a{i}"} for i in range(10)),
        probe=None,
        oracle=PassOracle(),
        max_steps=3,
    )
    result = EvalRunner(bridge).run_trial(task, 1)
    assert result.steps == 3


# -- aggregation -----------------------------------------------------------


def test_flaky_tasks_are_identified():
    calls = {"n": 0}

    def flip(ctx):
        calls["n"] += 1
        return {"flag": calls["n"] % 2 == 1, "steps": 1}

    suite = EvalRunner(RecordingBridge()).run_suite([_task(probe=flip)], trials=4)

    summary = suite.summaries[0]
    assert summary.flaky is True
    assert suite.to_dict()["flakyTasks"] == ["T1"]


def test_feasible_and_infeasible_are_scored_on_separate_axes():
    """Anti-'infeasible hacking': impossible tasks must not pad the headline rate."""
    tasks = [
        _task(id="FEASIBLE", oracle=FailOracle()),
        _task(id="INFEASIBLE", feasible=False, oracle=PassOracle()),
    ]
    data = EvalRunner(RecordingBridge()).run_suite(tasks, trials=2).to_dict()

    assert data["feasible"]["tasks"] == 1
    assert data["feasible"]["passes"] == 0
    assert data["infeasible"]["tasks"] == 1
    assert data["infeasible"]["passes"] == 2
    # the failing feasible task must not be rescued by the infeasible passes
    assert data["feasible"]["successRate"] == 0.0


def test_suite_result_serializes_with_confidence_intervals():
    suite = EvalRunner(RecordingBridge()).run_suite([_task()], trials=3)
    data = suite.to_dict()

    assert data["trialsPerTask"] == 3
    assert len(data["feasible"]["ci95"]) == 2
    assert data["tasks"][0]["taskId"] == "T1"
    assert "meanRoundTrips" in data["tasks"][0]
    assert data["startedAt"] and data["finishedAt"]


def test_runner_rejects_zero_trials():
    with pytest.raises(ValueError, match="trials must be"):
        EvalRunner(RecordingBridge()).run_suite([_task()], trials=0)


def test_task_summary_success_rate_and_empty_suite():
    empty = SuiteResult(label="l", tier="a1", trials=1).to_dict()
    assert empty["feasible"]["successRate"] == 0.0

    summary = TaskSummary(
        task_id="X", tier="a1", app="none", feasible=True, trials=4, passes=1
    )
    assert summary.success_rate == 0.25
    assert summary.flaky is True


# -- app gating ------------------------------------------------------------


class ForegroundBridge(RecordingBridge):
    """Bridge whose foreground window the test controls."""

    def __init__(self, process="Explorer.EXE", title=""):
        super().__init__()
        self._process = process
        self._title = title

    def observe(self, screenshot=True):
        self.calls.append(("observe", screenshot))
        return {
            "ok": True,
            "observation": {"activeWindow": {"process": self._process, "title": self._title}},
        }


def test_gated_probe_refuses_to_measure_the_wrong_window():
    """Regression: the first live A2 run measured the Windows shell for EVERY app
    and reported PASS — including for KiCad, which was not installed."""
    from desktop_worker.eval.suite import gated

    def never_runs(ctx):
        raise AssertionError("probe must not run when the wrong window is focused")

    probe = gated(never_runs, r"Blender", "idsStable")
    ctx = type("C", (), {"bridge": ForegroundBridge(process="Explorer.EXE", title="")})()

    payload = probe(ctx)
    assert payload["idsStable"] is False
    assert payload["notMeasured"] is True
    assert "NOT MEASURED" in payload["idsStableReason"]
    assert "Explorer.EXE" in payload["idsStableReason"]


def test_gated_probe_runs_when_the_right_window_is_focused():
    from desktop_worker.eval.suite import gated

    probe = gated(lambda ctx: {"idsStable": True, "steps": 1}, r"Blender", "idsStable")
    ctx = type("C", (), {"bridge": ForegroundBridge(process="blender.exe",
                                                    title="(Unsaved) - Blender 4.5")})()

    assert probe(ctx)["idsStable"] is True


def test_gated_probe_failure_is_scored_as_a_failure():
    """A NOT MEASURED payload must FAIL the oracle, never pass silently."""
    from desktop_worker.eval.oracles import ProbeFlag
    from desktop_worker.eval.suite import gated

    probe = gated(lambda ctx: {"idsStable": True}, r"KiCad", "idsStable")
    ctx = type("C", (), {"bridge": ForegroundBridge(process="Explorer.EXE", title="")})()

    verdict = ProbeFlag("idsStable").check(ctx, probe(ctx))
    assert verdict.passed is False
    assert "NOT MEASURED" in verdict.reason
