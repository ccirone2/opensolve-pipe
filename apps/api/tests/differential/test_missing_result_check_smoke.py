"""Smoke test of the deletion scan of the missing-result check (``missing_result_check``, TSD
§10.4): 25 seeds of each fuzz profile go through the same scan as ``python -m
tests.differential.missing_result_check``. On every converged network
``checks.missing_result_problems`` must report nothing on the result as solved, and must report
each pump and valve result deleted in turn. The seeds must reach every place a deleted result
sits in the full run (a pump or valve with both ports headed, a pump with one or both ports
without a head, a valve with both without), so that a scan that deleted nothing would fail here;
and a check that reports nothing, or reports a result as solved, fails the scan. The full run
over the profiles' 9,000 seeds is the command-line tool."""

from typing import Any

import pytest

pytest.importorskip("wntr")  # checks reads EPANET results (a dev dependency, so CI runs this)

from tests.differential import checks as ck
from tests.differential import missing_result_check as mrc
from tests.differential.generator import ASSIGNED_FLOW, DEFAULT, FLOW_CONTROL

SMOKE = (
    (DEFAULT, range(0, 25)),
    (FLOW_CONTROL, range(10_000, 10_025)),
    (ASSIGNED_FLOW, range(20_000, 20_025)),
)
PLACES = {("pump", 0), ("pump", 1), ("pump", 2), ("valve", 0), ("valve", 2)}
"""(kind, ports without a head) of the deleted results of the full run (TSD §10.4)."""


def test_every_deleted_result_is_reported_and_no_result_as_solved() -> None:
    records = [r for profile, seeds in SMOKE for r in mrc.check_seeds(seeds, profile)]
    assert mrc.failures(records) == []
    assert sum(r["outcome"] == "converged" for r in records) > len(records) * 9 // 10
    deleted = mrc.counts(records)
    assert set(deleted) == PLACES, deleted
    assert all(reported == n for n, reported in deleted.values()), deleted


def test_the_command_line_exits_0_when_every_deletion_is_reported(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as end:
        mrc.main(["0", "5", "--workers", "1"])
    assert end.value.code == 0
    out = capsys.readouterr().out
    assert "converged networks: 5" in out
    assert "deletions not reported: 0" in out
    assert "results as solved reported: 0" in out


@pytest.mark.parametrize("blind", [True, False])
def test_a_wrong_check_fails_the_scan(
    blind: bool, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A check that reports nothing misses every deletion; one that reports every element
    reports the results as solved. Either way the scan fails and the command exits 1."""
    real = ck.missing_result_problems

    def wrong(*args: Any) -> list[str]:
        return [] if blind else [*real(*args), "no result for X: made up"]

    monkeypatch.setattr(ck, "missing_result_problems", wrong)
    records = mrc.check_seeds(range(0, 3), DEFAULT)
    failures = mrc.failures(records)
    deleted = sum(n for n, _ in mrc.counts(records).values())
    assert deleted > 0
    if blind:
        assert len(failures) == deleted
        assert all(f.endswith("deleted, not reported") for f in failures)
        line = f"deletions not reported: {deleted}"
    else:
        assert len(failures) == 3
        assert all("result as solved reported" in f for f in failures)
        line = "results as solved reported: 3"
    with pytest.raises(SystemExit) as end:
        mrc.main(["0", "3", "--workers", "1"])
    assert end.value.code == 1
    assert line in capsys.readouterr().out.splitlines()
