"""Deterministic oracles (Phase 10).

An oracle answers "did this actually work?" by inspecting real state — a file on
disk, a window title, the clipboard, the perceived element list — never by asking
a model. Deterministic verifiers align with human judgment far better than
LLM-as-judge (94.1% vs 79.2% task-level in a 2026 study), and they are free, fast
and reproducible.

Every oracle returns a structured :class:`Verdict`, never a bare bool: a failing
measurement that cannot say WHY is nearly useless when you are chasing a
regression.

LLM critics are deliberately absent. They belong only where no oracle can exist,
and no task in the seed suite is in that category.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class Verdict:
    """Result of checking one oracle."""

    passed: bool
    reason: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "reason": self.reason, "detail": self.detail}


class Oracle:
    """Base oracle. Subclasses implement :meth:`check`.

    ``ctx`` is the runner-supplied context (see ``runner.EvalContext``); ``payload``
    is whatever the task's probe returned, or the last action result.
    """

    name = "oracle"

    def check(self, ctx: Any, payload: dict[str, Any]) -> Verdict:  # pragma: no cover
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name}>"


# --------------------------------------------------------------------------
# File-system oracles
# --------------------------------------------------------------------------


class FileExists(Oracle):
    """Pass when a path exists on disk."""

    name = "file_exists"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def check(self, ctx: Any, payload: dict[str, Any]) -> Verdict:
        exists = self.path.exists()
        return Verdict(
            exists,
            f"{self.path} {'exists' if exists else 'does not exist'}",
            {"path": str(self.path)},
        )


class FileContains(Oracle):
    """Pass when a file exists AND its text contains ``needle``."""

    name = "file_contains"

    def __init__(self, path: str | Path, needle: str) -> None:
        self.path = Path(path)
        self.needle = needle

    def check(self, ctx: Any, payload: dict[str, Any]) -> Verdict:
        if not self.path.exists():
            return Verdict(False, f"{self.path} does not exist", {"path": str(self.path)})
        try:
            text = self.path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return Verdict(False, f"cannot read {self.path}: {exc}", {"path": str(self.path)})
        hit = self.needle in text
        return Verdict(
            hit,
            f"{self.path} {'contains' if hit else 'does not contain'} {self.needle!r}",
            {"path": str(self.path), "length": len(text)},
        )


# --------------------------------------------------------------------------
# Desktop-state oracles
# --------------------------------------------------------------------------


class WindowTitleMatches(Oracle):
    """Pass when the active window title matches a regex."""

    name = "window_title_matches"

    def __init__(self, pattern: str) -> None:
        self.pattern = re.compile(pattern, re.IGNORECASE)

    def check(self, ctx: Any, payload: dict[str, Any]) -> Verdict:
        obs = ctx.bridge.observe(screenshot=False)
        window = (obs.get("observation") or {}).get("activeWindow") or {}
        title = window.get("title") or ""
        hit = bool(self.pattern.search(title))
        return Verdict(
            hit,
            f"active window title {title!r} "
            f"{'matches' if hit else 'does not match'} /{self.pattern.pattern}/",
            {"title": title},
        )


class ClipboardEquals(Oracle):
    """Pass when the clipboard holds exactly ``text``."""

    name = "clipboard_equals"

    def __init__(self, text: str) -> None:
        self.text = text

    def check(self, ctx: Any, payload: dict[str, Any]) -> Verdict:
        res = ctx.bridge.clipboard_get()
        got = ((res.get("detail") or {}).get("text")) or ""
        hit = got == self.text
        return Verdict(
            hit,
            "clipboard matches" if hit else f"clipboard is {got!r}, expected {self.text!r}",
            {"got": got},
        )


class ElementPresent(Oracle):
    """Pass when perception surfaces an element matching text and/or control type.

    This is the oracle that grades DW-PERCEIVE-RANK: the question is not "is the
    control on screen" but "did the agent get told about it".
    """

    name = "element_present"

    def __init__(self, text: Optional[str] = None, control_type: Optional[str] = None) -> None:
        if text is None and control_type is None:
            raise ValueError("ElementPresent needs text and/or control_type")
        self.text = (text or "").lower()
        self.control_type = (control_type or "").lower()

    def _matches(self, element: dict[str, Any]) -> bool:
        if self.text:
            haystack = f"{element.get('text') or ''} {element.get('label') or ''}".lower()
            if self.text not in haystack:
                return False
        if self.control_type:
            if self.control_type != str(element.get("type") or "").lower():
                return False
        return True

    def check(self, ctx: Any, payload: dict[str, Any]) -> Verdict:
        # Prefer elements the probe already collected so we do not pay for a
        # second perceive (and so the oracle grades the SAME observation).
        elements = payload.get("elements")
        if elements is None:
            elements = (ctx.bridge.perceive(screenshot=False) or {}).get("elements") or []
        hits = [e for e in elements if self._matches(e)]
        want = self.text or self.control_type
        return Verdict(
            bool(hits),
            f"{len(hits)} element(s) match {want!r} out of {len(elements)} perceived",
            {"matched": hits[:3], "perceivedCount": len(elements)},
        )


class StateChanged(Oracle):
    """Pass when the observation signature differs before vs after the actions.

    Guards against the silent no-op: an action that reports success but moved
    nothing. ``expect_change=False`` inverts it (used by settle/no-op tasks).
    """

    name = "state_changed"

    def __init__(self, expect_change: bool = True) -> None:
        self.expect_change = expect_change

    def check(self, ctx: Any, payload: dict[str, Any]) -> Verdict:
        before = payload.get("signatureBefore")
        after = payload.get("signatureAfter")
        if before is None or after is None:
            return Verdict(False, "probe did not record before/after signatures", {})
        changed = before != after
        ok = changed is self.expect_change
        return Verdict(
            ok,
            f"state {'changed' if changed else 'unchanged'} "
            f"(expected {'change' if self.expect_change else 'no change'})",
            {"changed": changed},
        )


class ProbeFlag(Oracle):
    """Pass when the probe's returned dict has ``key`` truthy.

    The general-purpose oracle for capability probes — the probe does the
    measuring and states its own verdict under a named flag.
    """

    name = "probe_flag"

    def __init__(self, key: str, expected: bool = True) -> None:
        self.key = key
        self.expected = expected

    def check(self, ctx: Any, payload: dict[str, Any]) -> Verdict:
        got = bool(payload.get(self.key))
        ok = got is self.expected
        note = payload.get(f"{self.key}Reason") or payload.get("reason") or ""
        return Verdict(
            ok,
            f"probe flag {self.key}={got} (expected {self.expected})"
            + (f": {note}" if note else ""),
            {k: v for k, v in payload.items() if k != "elements"},
        )


class ReportedInfeasible(Oracle):
    """For infeasible tasks: pass when the run correctly reported impossibility.

    Scored on a separate axis from feasible tasks so that a weak agent cannot pad
    its headline success rate by "completing" impossible work.
    """

    name = "reported_infeasible"

    def check(self, ctx: Any, payload: dict[str, Any]) -> Verdict:
        refused = bool(payload.get("refused") or payload.get("blocked"))
        ok_false = payload.get("ok") is False
        good = refused or ok_false
        return Verdict(
            good,
            "correctly refused / reported failure"
            if good
            else "claimed success on an infeasible task",
            {"payloadOk": payload.get("ok"), "refused": refused},
        )


# --------------------------------------------------------------------------
# Composites
# --------------------------------------------------------------------------


class AllOf(Oracle):
    """Pass only when every child oracle passes."""

    name = "all_of"

    def __init__(self, *oracles: Oracle) -> None:
        if not oracles:
            raise ValueError("AllOf needs at least one oracle")
        self.oracles = oracles

    def check(self, ctx: Any, payload: dict[str, Any]) -> Verdict:
        verdicts = [o.check(ctx, payload) for o in self.oracles]
        failed = [v for v in verdicts if not v.passed]
        return Verdict(
            not failed,
            "all checks passed"
            if not failed
            else "; ".join(v.reason for v in failed),
            {"checks": [v.to_dict() for v in verdicts]},
        )


class AnyOf(Oracle):
    """Pass when at least one child oracle passes."""

    name = "any_of"

    def __init__(self, *oracles: Oracle) -> None:
        if not oracles:
            raise ValueError("AnyOf needs at least one oracle")
        self.oracles = oracles

    def check(self, ctx: Any, payload: dict[str, Any]) -> Verdict:
        verdicts = [o.check(ctx, payload) for o in self.oracles]
        passed = [v for v in verdicts if v.passed]
        return Verdict(
            bool(passed),
            passed[0].reason if passed else "; ".join(v.reason for v in verdicts),
            {"checks": [v.to_dict() for v in verdicts]},
        )
