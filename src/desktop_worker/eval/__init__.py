"""Evaluation harness (Phase 10) — measure before you optimise.

Three tiers, because measurement must not be expensive to run:

* **A1** — Null backends, CI, zero Claude quota. Contract + safety invariants.
* **A2** — live desktop, zero Claude quota. Grades the TOOL SURFACE, which is what
  Phase 11 changes.
* **B**  — full AI task runs. Spends Claude quota; opt-in only.

The harness observes the system under test and never modifies it — otherwise every
measurement taken after a change would be comparing two different systems.
"""

from desktop_worker.eval.oracles import (
    AllOf,
    AnyOf,
    ClipboardEquals,
    ElementPresent,
    FileContains,
    FileExists,
    Oracle,
    ProbeFlag,
    ReportedInfeasible,
    StateChanged,
    Verdict,
    WindowTitleMatches,
)
from desktop_worker.eval.runner import CountingBridge, EvalContext, EvalRunner
from desktop_worker.eval.spec import (
    TIERS,
    EvalResult,
    EvalTask,
    SuiteResult,
    TaskSummary,
    wilson_interval,
)
from desktop_worker.eval.suite import all_tasks, tier_a1_tasks, tier_a2_tasks, tier_b_tasks

__all__ = [
    "TIERS",
    "AllOf",
    "AnyOf",
    "ClipboardEquals",
    "CountingBridge",
    "ElementPresent",
    "EvalContext",
    "EvalResult",
    "EvalRunner",
    "EvalTask",
    "FileContains",
    "FileExists",
    "Oracle",
    "ProbeFlag",
    "ReportedInfeasible",
    "StateChanged",
    "SuiteResult",
    "TaskSummary",
    "Verdict",
    "WindowTitleMatches",
    "all_tasks",
    "tier_a1_tasks",
    "tier_a2_tasks",
    "tier_b_tasks",
    "wilson_interval",
]
