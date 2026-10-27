"""Smoke test of the design-checks corpus check (``design_checks_check``, proposal
design-checks.md §6): the reference cases, the unit-test data networks and a few seeds of each
fuzz profile go through the same checks as ``python -m tests.differential.design_checks_check``,
and none may differ. The selection must reach every check passing and failing, and a check not
evaluated, so that a check that compared nothing would fail here; and the checks themselves must
catch falsified results and a solved value that changed."""

import copy
from collections import Counter
from typing import Any

import pytest

from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import SolvedState
from opensolve_pipe.services.solver import solve_project
from tests.differential import design_checks_check
from tests.differential.corpus import items, load
from tests.differential.design_checks_check import (
    CHECK_IDS,
    NO_CURVES,
    _dump,
    check,
    check_all,
    result_problems,
    summarize,
    with_checks,
    with_curves,
)

SMOKE_FUZZ = (
    [f"fuzz_{s}" for s in range(30)]
    + [f"fuzzfc_{s}" for s in range(10_000, 10_020)]
    + [f"fuzzaf_{s}" for s in range(20_000, 20_020)]
)


def test_the_smoke_selection_has_no_difference_and_reaches_every_outcome() -> None:
    selection = [
        t for t in items() if t[0].startswith(("ref_", "unit_")) or t[0] in set(SMOKE_FUZZ)
    ]
    records = check_all(selection, workers=1)
    report = summarize(records)
    assert report[-1] == "different: 0", "\n".join(report)
    outcomes: Counter[str] = Counter()
    for r in records:
        outcomes.update(r.get("outcomes", {}))
    for check_id in CHECK_IDS:
        for outcome in ("pass", "fail"):
            assert outcomes[f"{check_id}:{outcome}"] > 0, (check_id, outcome, outcomes)
    assert sum(n for k, n in outcomes.items() if k.endswith(":not_evaluated")) > 0
    assert {r["profile"] for r in records} >= {"ref", "unit", "fuzz", "fuzzfc", "fuzzaf"}


def _case() -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """B's project, solved state (without its results) and results of a reference case with a
    pump, every check reported."""
    _, spec = next(t for t in items() if t[0] == "ref_npsh_margin_standard_atmosphere")
    data = with_checks(with_curves(load(spec).model_dump(mode="json", by_alias=True)))
    state = _dump(solve_project(Project.model_validate(data), NO_CURVES))
    reported = state.pop("designChecks")
    assert {r["check"] for r in reported} >= {"npsh_margin", "operating_region", "pipe_velocity"}
    return data, state, reported


def test_falsified_results_are_caught() -> None:
    data, state, reported = _case()
    assert result_problems(data, state, reported) == []
    for falsify in (
        lambda rs: rs[0].update(outcome="fail" if rs[0]["outcome"] != "fail" else "pass"),
        lambda rs: rs[-1].update(value=(rs[-1]["value"] or 1.0) * (1 + 1e-15)),
        lambda rs: rs[0]["limits"].update(min=1.0),
        lambda rs: rs.pop(),
        lambda rs: rs.reverse(),
        lambda rs: rs[-1].update(pipesOutside=[0, 1]),
    ):
        changed = copy.deepcopy(reported)
        falsify(changed)
        assert result_problems(data, state, changed), falsify


def test_the_npsh_requirement_is_the_greater_term() -> None:
    """(b)'s NPSH rule against the reported limit: max(NPSHr + margin, ratio × NPSHr)."""
    _, state, reported = _case()
    [npsh] = [r for r in reported if r["check"] == "npsh_margin"]
    pump = state["pumpResults"][npsh["componentId"]]
    assert npsh["outcome"] == "pass"
    npshr = pump["npshRequired"]
    assert npsh["limits"]["min"] == max(npshr + 1.0, 1.1 * npshr)
    assert pump["npshAvailable"] >= npsh["limits"]["min"]


def test_a_solved_value_changed_by_the_checks_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    """(a): a solve with checks whose state differs from the one without is a difference."""
    solve = design_checks_check.solve_project

    def nudged(project: Project, options: object = None) -> SolvedState:
        state = solve(project, NO_CURVES)
        if project.settings.design_checks is not None:
            link = next(iter(state.link_results.values()))
            link.flow = link.flow * (1 + 1e-15) + 1e-300
        return state

    monkeypatch.setattr(design_checks_check, "solve_project", nudged)
    _, spec = next(t for t in items() if t[0] == "ref_npsh_margin_standard_atmosphere")
    record = check("ref_npsh_margin_standard_atmosphere", load(spec))
    assert record["outcome"] == "different"
    assert any(d.startswith("(a) B's solved state differs") for d in record["differences"])
