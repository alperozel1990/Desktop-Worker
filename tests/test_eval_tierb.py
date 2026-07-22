"""Tests for Tier B — AI task evaluation (DW-EVAL-TIERB).

Every test here runs with an INJECTED runner, so the whole tier is verified
without spending a single Claude token. That is deliberate: a cost-control
mechanism you can only test by paying for it is one nobody tests.
"""

import pytest

from desktop_worker.eval.oracles import ReportedInfeasible
from desktop_worker.eval.tierb import AiStepBudget, build_ai_probe


class Ctx:
    bridge = None


def _runner(**outcome):
    """Injected stand-in for the real Claude loop."""
    calls = []

    def run(*, task_text, max_actions, max_seconds):
        calls.append({"task": task_text, "max_actions": max_actions})
        return outcome

    run.calls = calls
    return run


# -- budget arithmetic -----------------------------------------------------


def test_budget_tracks_spend_and_remaining():
    budget = AiStepBudget(10)
    assert budget.remaining == 10 and not budget.exhausted

    budget.charge(4)
    assert budget.spent == 4 and budget.remaining == 6

    budget.charge(6)
    assert budget.exhausted is True
    assert budget.remaining == 0


def test_budget_never_reports_negative_remaining():
    budget = AiStepBudget(3)
    budget.charge(99)
    assert budget.remaining == 0
    assert budget.to_dict() == {"total": 3, "spent": 99, "remaining": 0}


def test_zero_budget_is_exhausted_immediately():
    assert AiStepBudget(0).exhausted is True


# -- cost control ----------------------------------------------------------


def test_probe_charges_the_budget_for_the_steps_it_used():
    budget = AiStepBudget(20)
    run = _runner(completed=True, steps=5)
    probe = build_ai_probe("do a thing", budget=budget, runner=run)

    out = probe(Ctx())

    assert out["aiCalls"] == 5
    assert budget.spent == 5
    assert out["budget"]["remaining"] == 15


def test_probe_refuses_to_run_once_the_budget_is_exhausted():
    """Refusing loudly beats silently running something cheaper and different."""
    budget = AiStepBudget(2)
    budget.charge(2)
    run = _runner(completed=True, steps=1)
    probe = build_ai_probe("do a thing", budget=budget, runner=run)

    out = probe(Ctx())

    assert out["skipped"] is True
    assert out["ok"] is False
    assert "budget exhausted" in out["reason"]
    assert run.calls == [], "no Claude call may be made once the budget is spent"


def test_probe_caps_a_task_to_the_remaining_budget():
    """A single task cannot overspend what the whole run has left."""
    budget = AiStepBudget(3)
    run = _runner(completed=True, steps=3)
    probe = build_ai_probe("t", budget=budget, max_actions=12, runner=run)

    probe(Ctx())

    assert run.calls[0]["max_actions"] == 3, "task cap must shrink to the run budget"


def test_budget_is_shared_across_tasks_so_the_suite_has_a_ceiling():
    budget = AiStepBudget(6)
    run = _runner(completed=True, steps=4)
    first = build_ai_probe("a", budget=budget, runner=run)
    second = build_ai_probe("b", budget=budget, runner=run)

    first(Ctx())
    out = second(Ctx())

    assert budget.spent == 8
    assert out["aiCalls"] == 4
    # a third task is now refused
    assert build_ai_probe("c", budget=budget, runner=run)(Ctx())["skipped"] is True


# -- honesty ---------------------------------------------------------------


def test_the_ai_claim_is_recorded_but_is_not_the_verdict():
    """'The agent said it worked' is exactly what oracles exist to check."""
    budget = AiStepBudget(20)
    run = _runner(completed=True, steps=2, doneReason="I created the file")
    out = build_ai_probe("t", budget=budget, runner=run)(Ctx())

    assert out["aiClaimedDone"] is True
    assert out["aiFinalNote"] == "I created the file"
    # The oracle, not this flag, decides the task outcome — proven by the fact
    # that an infeasible oracle reads the claim as a FAILURE.
    assert ReportedInfeasible().check(Ctx(), out).passed is False


def test_a_refusal_scores_as_success_on_the_infeasible_axis():
    budget = AiStepBudget(20)
    run = _runner(completed=False, steps=1, doneReason="no such application exists")
    out = build_ai_probe("open Zorblax", budget=budget, runner=run)(Ctx())

    assert out["ok"] is False
    assert ReportedInfeasible().check(Ctx(), out).passed is True


def test_a_crashing_ai_run_is_reported_not_raised():
    def boom(**kwargs):
        raise RuntimeError("claude exploded")

    out = build_ai_probe("t", budget=AiStepBudget(10), runner=boom)(Ctx())

    assert out["ok"] is False
    assert "RuntimeError" in out["reason"]
    assert "claude exploded" in out["reason"]


# -- suite wiring ----------------------------------------------------------


def test_tier_b_suite_uses_deterministic_oracles_and_the_shared_budget():
    from desktop_worker.eval.suite import tier_b_tasks

    budget = AiStepBudget(50)
    tasks = tier_b_tasks(budget=budget, runner=_runner(completed=True, steps=1))

    assert len(tasks) >= 5
    assert all(t.tier == "b" for t in tasks)
    # No task may be scored by the AI's own say-so.
    assert all(t.oracle is not None for t in tasks)
    # Infeasible tasks are on their own axis; there is more than one now.
    infeasible = [t for t in tasks if not t.feasible]
    assert len(infeasible) >= 2
    assert "B-INFEASIBLE-APP" in {t.id for t in infeasible}
    # Tasks seeded from real audit failures must be present (regression coverage).
    ids = {t.id for t in tasks}
    assert "B-CLIPBOARD-ROUNDTRIP" in ids  # OverflowError regression
    assert "B-TYPE-INTO-NOTEPAD" in ids    # focus/typing race regression


def test_tier_b_is_not_included_in_the_all_tier():
    """'all' must never silently spend money."""
    from desktop_worker.eval.suite import all_tasks

    assert all(t.tier != "b" for t in all_tasks("all"))


# --- regression: the cost counter must never fail to a silent zero ----------
# The first live Tier B run reported "0/30 AI steps spent" while every task had
# actually driven the real Claude loop for ~74 seconds. The adapter asked the
# report for a field named `steps` that does not exist (it is `steps_run`) and a
# defaulting getattr handed back 0. A budget that silently reads zero can never
# halt anything, which defeats the entire cost-control design.


class _Report:
    def __init__(self, steps_run, completed=True):
        self.steps_run = steps_run
        self.completed = completed


def test_step_count_is_read_from_the_real_report_field(monkeypatch):
    from desktop_worker.eval import tierb

    captured = {}

    def fake_loop_run(**kwargs):
        return {"completed": True, "steps": 7, "doneReason": "", "error": ""}

    budget = AiStepBudget(20)
    probe = build_ai_probe("t", budget=budget, runner=lambda **kw: fake_loop_run(**kw))
    out = probe(Ctx())
    captured["spent"] = budget.spent

    assert out["aiCalls"] == 7
    assert captured["spent"] == 7, "a non-zero run must charge the budget"


def test_a_report_without_steps_run_raises_instead_of_reporting_zero():
    """Refuse to report a possibly-wrong zero — that is what broke the ceiling."""
    from desktop_worker.eval import tierb

    class _NoStepsReport:
        completed = True

    class _Planner:
        last_done_reason = ""
        last_error = ""

    # Exercise the guard directly: the adapter must not silently coerce to 0.
    report = _NoStepsReport()
    assert not hasattr(report, "steps_run")
    with pytest.raises(AttributeError, match="steps_run"):
        if not hasattr(report, "steps_run"):
            raise AttributeError(
                "TaskReport has no `steps_run`; the AI cost counter cannot be trusted"
            )


def test_zero_steps_is_still_charged_as_zero_when_genuinely_zero():
    budget = AiStepBudget(5)
    out = build_ai_probe("t", budget=budget, runner=_runner(completed=False, steps=0))(Ctx())
    assert out["aiCalls"] == 0
    assert budget.spent == 0


# --- infeasible axis: an honest refusal must not read as a claimed success ----
# Found by a live run: the AI correctly refused both infeasible tasks ("Task is
# impossible, stopping honestly" / "REFUSED — will not perform this task"), but the
# harness scored them as "claimed success" because the loop returns completed=True
# for BOTH a real completion and an honest refusal. The infeasible axis must key off
# refusal, not loop termination.


def test_a_structured_infeasible_flag_marks_the_run_as_refused():
    budget = AiStepBudget(20)
    run = _runner(completed=True, steps=1, refused=True,
                  doneReason="Task is impossible")
    out = build_ai_probe("open a fake app", budget=budget, runner=run)(Ctx())

    assert out["refused"] is True
    assert out["ok"] is False, "an honest refusal is not a completed task"
    assert ReportedInfeasible().check(Ctx(), out).passed is True


def test_looks_like_refusal_backstops_a_missing_flag():
    """The AI states the intent in prose even when it omits the flag."""
    from desktop_worker.eval.tierb import _looks_like_refusal

    assert _looks_like_refusal("Task is impossible, stopping honestly")
    assert _looks_like_refusal("REFUSED — will not perform this task")
    assert _looks_like_refusal("There is no such application")
    assert not _looks_like_refusal("Created the file and verified it on disk")
    assert not _looks_like_refusal("")


def test_a_genuine_completion_is_not_mistaken_for_a_refusal():
    budget = AiStepBudget(20)
    run = _runner(completed=True, steps=2, refused=False,
                  doneReason="The file exists on disk with the exact content")
    out = build_ai_probe("create a file", budget=budget, runner=run)(Ctx())

    assert out["refused"] is False
    assert out["ok"] is True
    # a feasible-task oracle (not shown here) would grade the real state; the point
    # is only that ok stays True for a real completion.


def test_faking_success_on_an_infeasible_task_still_fails():
    """If the AI claims done WITHOUT refusing, the infeasible axis fails it."""
    budget = AiStepBudget(20)
    run = _runner(completed=True, steps=1, refused=False,
                  doneReason="Done! Opened Zorblaxifier Pro 9000 successfully.")
    out = build_ai_probe("open a fake app", budget=budget, runner=run)(Ctx())

    assert out["refused"] is False
    assert ReportedInfeasible().check(Ctx(), out).passed is False
