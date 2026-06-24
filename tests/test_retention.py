"""Tests for artifact retention (Phase 7). Pure decision + injected IO."""

from desktop_worker.audit.retention import prune_artifacts, select_for_pruning

DAY = 86_400


def test_select_by_age():
    now = 100 * DAY
    entries = [("old", 10 * DAY), ("recent", 99 * DAY)]
    doomed = select_for_pruning(entries, max_age_days=30, now=now)
    assert doomed == ["old"]


def test_select_by_count_keeps_newest():
    now = 100 * DAY
    entries = [("a", 1), ("b", 2), ("c", 3), ("d", 4)]
    doomed = select_for_pruning(entries, max_count=2, now=now)
    assert doomed == ["a", "b"]  # oldest two pruned, newest two kept


def test_select_age_and_count_combined():
    now = 100 * DAY
    entries = [("ancient", 1 * DAY), ("old", 20 * DAY),
               ("mid", 80 * DAY), ("new", 99 * DAY)]
    # age prunes ancient+old (older than 30d); count keeps newest 1 of survivors
    doomed = select_for_pruning(entries, max_age_days=30, max_count=1, now=now)
    assert "ancient" in doomed and "old" in doomed and "mid" in doomed
    assert "new" not in doomed


def test_select_nothing_when_within_limits():
    now = 100 * DAY
    entries = [("a", 99 * DAY), ("b", 98 * DAY)]
    assert select_for_pruning(entries, max_age_days=30, max_count=10, now=now) == []


def test_prune_artifacts_noop_without_limits():
    removed = prune_artifacts("X", scan=lambda d: [("a", 1)], remove=_fail_remove)
    assert removed == []


def _fail_remove(_p):
    raise AssertionError("should not remove anything")


def test_prune_artifacts_removes_and_returns():
    removed_paths = []
    entries = [("old", 1 * DAY), ("new", 99 * DAY)]
    removed = prune_artifacts("X", max_age_days=30, now=lambda: 100 * DAY,
                              scan=lambda d: entries,
                              remove=lambda p: removed_paths.append(p))
    assert removed == ["old"]
    assert removed_paths == ["old"]
