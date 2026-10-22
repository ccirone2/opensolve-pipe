"""Smoke test of the EPANET differential fuzz (TSD §10.4).

Seeds 0-49 go through the same classification as ``python -m tests.differential.fuzz``, with the
real EPANET 2.2 run (WNTR, a dev dependency; the test is skipped only where WNTR is not
installed). For every seed our solver must converge, EPANET must run (an iteration count in the
record), the seed must not be critical (``classes.is_critical``: a converged result of ours that
fails the independent checks), and its class must be the one pinned in ``CLASSES``. A harness or
EPANET failure (a library that does not load, a WNTR change) therefore fails the test instead of
leaving nothing compared.

The classification is deterministic: the same under any PYTHONHASHSEED (checked under 0 and
12345). A change in a seed's class is a change in our solver's or EPANET's behaviour on that
network, to be reviewed (``python -m tests.differential.fuzz SEED SEED+1 --out DIR`` writes its
record and reproducer), not a number to update blindly. The 50 seeds take about 10 s; the full
run of 3,000 seeds is the command-line tool.

The generator profile 'flow_control' (flow-controlled pumps, CLAUDE.md D11) is pinned the same
way on its seeds 10,000-10,024 (``FLOW_CONTROL_CLASSES``, deterministic under PYTHONHASHSEED 0
and 12345), with the controlled-pump search of every converged network (no network with distinct
valid solutions that differ in flowing state), and the seeds together must reach every control
state (active, max_speed, min_speed, no_flow, off). They take about 15 s (the state search
solves each network up to 16 more times); the 3,000-seed run is the command-line tool
(``--profile flow_control``, seeds 10,000-12,999). Three seeds of that run whose statuses cycle
are pinned too (``CYCLE_CLASSES``).
"""

import functools
from typing import Any

import pytest

from tests.differential.classes import is_critical

CLASSES = {
    "pass": "1 2 4 8 10 12 14 15 17 19 21 23 25 27 29 30 31 33 35 38 40 41 42 43 44 47 49",
    "documented": "5 9 16 18 24 36 37 39 48",
    "state_only_zero_flow": "3 6 7 28 32",
    "pass_ep_unbalanced": "0 11 13 22",
    "epanet_unbalanced": "20 26 34",
    "b_stagnant_heads": "45",
    "ours_verified_by_pinned_epanet": "46",
}
"""The seeds of each class (``fuzz`` status), as the 3,000-seed run of TSD §10.4 gives them."""

EXPECTED = {int(seed): cls for cls, seeds in CLASSES.items() for seed in seeds.split()}
SEEDS = range(0, 50)


def test_every_seed_has_one_class() -> None:
    assert sorted(EXPECTED) == list(SEEDS)
    assert sum(len(s.split()) for s in CLASSES.values()) == len(SEEDS)


DETAIL_KEYS = ("status", "error", "self_check", "ours_laws", "ours_rules", "mismatch", "state_diff")


def check_record(record: dict[str, Any], expected: str) -> None:
    """Not critical, our solver converged, EPANET ran, and the pinned class."""
    detail = {k: record.get(k) for k in DETAIL_KEYS}
    assert not is_critical(record), detail
    assert record.get("ours_converged") is True, detail
    iterations = record.get("ep_iterations")
    assert isinstance(iterations, int), detail
    assert iterations > 0, detail
    assert record["status"] == expected, detail


@pytest.mark.parametrize("seed", SEEDS)
def test_seed_classification(seed: int) -> None:
    # WNTR is a dev dependency, so this runs in CI; skip only where it is not installed.
    pytest.importorskip("wntr")
    from tests.differential.fuzz import run_seed

    check_record(run_seed(seed), EXPECTED[seed])


FLOW_CONTROL_CLASSES = {
    "pass": (
        "10000 10002 10003 10004 10006 10007 10008 10009 10010 10011 10012 10014 10016 10017"
        " 10020 10021 10022 10023 10024"
    ),
    "state_only_zero_flow": "10005 10013 10018 10019",
    "documented": "10001",
    "b_stagnant_heads": "10015",
}
"""The seeds of each class in the generator profile 'flow_control'."""

FLOW_CONTROL_EXPECTED = {
    int(seed): cls for cls, seeds in FLOW_CONTROL_CLASSES.items() for seed in seeds.split()
}
FLOW_CONTROL_SEEDS = range(10_000, 10_025)


@functools.cache
def flow_control_record(seed: int) -> dict[str, Any]:
    from tests.differential.fuzz import run_seed

    return run_seed(seed, profile="flow_control")


def test_every_flow_control_seed_has_one_class() -> None:
    assert sorted(FLOW_CONTROL_EXPECTED) == list(FLOW_CONTROL_SEEDS)
    n = sum(len(s.split()) for s in FLOW_CONTROL_CLASSES.values())
    assert n == len(FLOW_CONTROL_SEEDS)


@pytest.mark.parametrize("seed", FLOW_CONTROL_SEEDS)
def test_flow_control_seed_classification(seed: int) -> None:
    pytest.importorskip("wntr")
    record = flow_control_record(seed)
    check_record(record, FLOW_CONTROL_EXPECTED[seed])
    search = record.get("control_search")  # every converged network with one that is on
    assert search is None or not search["multiple"], search


CYCLE_CLASSES = {11_738: "pass", 12_703: "pass", 12_773: "documented"}
"""Flow-control seeds whose pump and valve statuses cycle after a step that changed several at
once, the cycle closed by a step that changes one. They converge since the single-change mode
also starts on such cycles (11,738 and 12,773) and, when it reaches a state again, goes back to
a state with a change not yet taken (12,703, ``status._backtrack``); before, all three ended not
converged."""


@pytest.mark.parametrize("seed", sorted(CYCLE_CLASSES))
def test_status_cycles_closed_by_one_change_converge(seed: int) -> None:
    pytest.importorskip("wntr")
    record = flow_control_record(seed)
    check_record(record, CYCLE_CLASSES[seed])
    search = record.get("control_search")
    assert search is None or not search["multiple"], search


def test_flow_control_seeds_reach_every_state() -> None:
    pytest.importorskip("wntr")
    states = {
        record["states_o"][pid]
        for record in map(flow_control_record, FLOW_CONTROL_SEEDS)
        for pid in record.get("controlled", [])
    }
    assert {"active", "max_speed", "min_speed", "no_flow", "off"} <= states, states
