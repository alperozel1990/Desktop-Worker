"""Artifact retention / cleanup (requirements Phase 7 — artifact retention).

Prunes old generated artifacts (session directories, screenshots, CLI captures)
by age and/or count so a long-running install does not grow without bound. The
pruning DECISION is a pure function (``select_for_pruning``) so it is fully
unit-testable with a fake clock and synthetic entries; the thin
``prune_artifacts`` wrapper does the filesystem IO and is also injectable.
"""

from __future__ import annotations

import os
import shutil
import time
from typing import Callable, Optional

_DAY_SECONDS = 86_400


def select_for_pruning(entries: list[tuple[str, float]], *,
                       max_age_days: Optional[float] = None,
                       max_count: Optional[int] = None,
                       now: float) -> list[str]:
    """Decide which entries to prune. Pure.

    ``entries`` is ``[(path, mtime_epoch_seconds), ...]``. An entry is pruned if
    it is older than ``max_age_days``; then, of the survivors, the oldest beyond
    ``max_count`` are also pruned. Returns paths oldest-first.
    """
    doomed: set[str] = set()
    if max_age_days is not None:
        cutoff = now - max_age_days * _DAY_SECONDS
        for path, mtime in entries:
            if mtime < cutoff:
                doomed.add(path)
    if max_count is not None:
        survivors = [(p, m) for (p, m) in entries if p not in doomed]
        if len(survivors) > max_count:
            # Keep the newest max_count; doom the rest (the oldest).
            by_new = sorted(survivors, key=lambda pm: pm[1], reverse=True)
            for path, _m in by_new[max_count:]:
                doomed.add(path)
    return [p for (p, _m) in sorted(entries, key=lambda pm: pm[1]) if p in doomed]


def _scan(directory: str) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    try:
        with os.scandir(directory) as it:
            for entry in it:
                try:
                    out.append((entry.path, entry.stat().st_mtime))
                except OSError:
                    continue
    except OSError:
        return []
    return out


def _default_remove(path: str) -> None:
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            os.remove(path)
        except OSError:
            pass


def prune_artifacts(directory: str, *, max_age_days: Optional[float] = None,
                    max_count: Optional[int] = None,
                    now: Callable[[], float] = time.time,
                    scan: Callable[[str], list[tuple[str, float]]] = _scan,
                    remove: Callable[[str], None] = _default_remove) -> list[str]:
    """Prune old entries directly under ``directory``; return removed paths.

    No-op (returns []) when neither ``max_age_days`` nor ``max_count`` is set, so
    a misconfigured call can never wipe everything.
    """
    if max_age_days is None and max_count is None:
        return []
    entries = scan(directory)
    doomed = select_for_pruning(entries, max_age_days=max_age_days,
                                max_count=max_count, now=now())
    for path in doomed:
        remove(path)
    return doomed
