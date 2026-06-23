"""Tests for the download wait + locate workflow (Phase 5). Pure, fake fs+clock."""

import os

from desktop_worker.workflows.downloads import (
    find_new_files,
    is_partial,
    snapshot,
    wait_for_download,
)


def test_is_partial_detects_markers():
    assert is_partial("movie.mp4.crdownload")
    assert is_partial("file.part")
    assert is_partial("x.TMP")
    assert is_partial("backup~")
    assert not is_partial("report.pdf")


def test_find_new_files_excludes_before_and_partials():
    before = {"old.txt"}
    listing = ["old.txt", "new.pdf", "wip.crdownload", "a.zip"]
    new = find_new_files(before, "D", listdir=lambda d: listing)
    assert new == ["a.zip", "new.pdf"]  # sorted, partial excluded


def test_snapshot_handles_missing_dir():
    assert snapshot("nope", listdir=_raise_oserror) == set()


def _raise_oserror(_d):
    raise OSError("no dir")


def test_wait_for_download_returns_completed_file():
    # Clock advances each call; the file appears on the 3rd poll.
    ticks = iter([0.0, 0.0, 0.5, 1.0, 1.5])
    states = [
        ["base"],                       # before snapshot
        ["base"],                       # poll 1: nothing new
        ["base", "f.zip.crdownload"],   # poll 2: still downloading
        ["base", "f.zip"],              # poll 3: done
    ]
    calls = {"n": 0}

    def listdir(_d):
        i = min(calls["n"], len(states) - 1)
        calls["n"] += 1
        return states[i]

    path = wait_for_download("D", timeout_s=10, poll_s=0.5,
                             now=lambda: next(ticks), sleep=lambda s: None,
                             listdir=listdir)
    assert path == os.path.join("D", "f.zip")


def test_wait_for_download_times_out():
    ticks = iter([0.0, 0.0, 1.0, 2.0, 3.0, 99.0])
    path = wait_for_download("D", before={"x"}, timeout_s=2.0, poll_s=0.5,
                             now=lambda: next(ticks), sleep=lambda s: None,
                             listdir=lambda d: ["x"])
    assert path is None


def test_wait_for_download_ignores_partial_only():
    # Only a partial file is ever present -> should time out (never completes).
    ticks = iter([0.0, 0.0, 5.0])
    path = wait_for_download("D", before=set(), timeout_s=1.0, poll_s=0.1,
                             now=lambda: next(ticks), sleep=lambda s: None,
                             listdir=lambda d: ["big.iso.crdownload"])
    assert path is None
