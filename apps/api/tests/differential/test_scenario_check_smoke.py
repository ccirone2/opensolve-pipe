"""Smoke test of the scenario corpus check (``scenario_check``, proposal scenario-manager.md
§7.3): the reference cases and 25 seeds of each fuzz profile go through the same checks as
``python -m tests.differential.scenario_check``, and none may differ. The seeds must also reach
every outcome the checks compare (a solve, an invalid value), so that a check that compared
nothing would fail here; the full corpus run is the command-line tool."""

from collections import Counter

from tests.differential.corpus import items
from tests.differential.scenario_check import check_all

SMOKE_FUZZ = (
    [f"fuzz_{s}" for s in range(25)]
    + [f"fuzzfc_{s}" for s in range(10_000, 10_025)]
    + [f"fuzzaf_{s}" for s in range(20_000, 20_025)]
)


def test_scenarios_over_the_reference_cases_and_fuzz_seeds() -> None:
    selection = [t for t in items() if t[0].startswith("ref_") or t[0] in SMOKE_FUZZ]
    assert len([t for t in selection if not t[0].startswith("ref_")]) == len(SMOKE_FUZZ)
    records = check_all(selection, curve_every=5)
    different = [f"{r['name']}: {'; '.join(r['differences'])}" for r in records if r["differences"]]
    assert not different, "\n".join(different)
    outcomes = Counter(r["outcome"] for r in records)
    assert outcomes["solved"] > len(records) // 2, outcomes
    assert outcomes["invalid"] >= 1, outcomes
    assert outcomes["load_error"] == 0, outcomes
    assert sum("curve" in r for r in records) >= 10
    assert sum(r.get("converged") is True for r in records) > len(records) // 2
