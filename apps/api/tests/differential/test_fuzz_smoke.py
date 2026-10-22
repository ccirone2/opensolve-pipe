"""Smoke test of the EPANET differential fuzz (TSD §10.4).

A fixed range of seeds goes through the same classification as ``python -m
tests.differential.fuzz``, with the real EPANET 2.2 run (WNTR, a dev dependency). No seed may be
critical (``classes.is_critical``): a converged result of ours that fails the independent checks.
Every seed must also be classified, so neither the harness nor our solver may raise. Seeds 0-49
fall in seven classes (pass, documented, state_only_zero_flow, pass_ep_unbalanced,
epanet_unbalanced, b_stagnant_heads, ours_verified_by_pinned_epanet) and take about 10 s; the
full run of 3,000 seeds is the command-line tool.
"""

import pytest

from tests.differential.classes import is_critical
from tests.differential.fuzz import run_seed

SEEDS = range(0, 50)


@pytest.mark.parametrize("seed", SEEDS)
def test_seed_is_not_critical(seed: int) -> None:
    record = run_seed(seed)
    assert record["status"] not in ("harness_error", "ours_exception"), record.get("error")
    detail = {k: record.get(k) for k in ("status", "self_check", "ours_laws", "ours_rules")}
    assert not is_critical(record), detail
