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
"""

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


@pytest.mark.parametrize("seed", SEEDS)
def test_seed_classification(seed: int) -> None:
    # WNTR is a dev dependency, so this runs in CI; skip only where it is not installed.
    pytest.importorskip("wntr")
    from tests.differential.fuzz import run_seed

    record = run_seed(seed)
    keys = ("status", "error", "self_check", "ours_laws", "ours_rules", "mismatch", "state_diff")
    detail = {k: record.get(k) for k in keys}
    assert not is_critical(record), detail
    assert record.get("ours_converged") is True, detail
    iterations = record.get("ep_iterations")
    assert isinstance(iterations, int), detail
    assert iterations > 0, detail
    assert record["status"] == EXPECTED[seed], detail
