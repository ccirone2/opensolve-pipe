"""Smoke test of the equipment corpus check (``equipment_check``, proposal
equipment-pressure-drop.md §7.4): the reference cases, the unit-test data networks and a few
seeds of each fuzz profile go through the same checks as
``python -m tests.differential.equipment_check``, and none may differ. The selection must reach
every replacement the check makes (a rated point, a Cv and a Kv, in every fuzz profile), a valve
without a result, an element in reverse flow and one in a floating section, so that a check that
compared nothing would fail here; and the checks themselves must catch an element whose law or
result was falsified, and the largest differences recorded must show a falsified law where D6
does not. The full corpus run is the command-line tool."""

import copy
import math
import random
from collections import Counter
from typing import Any

import pytest

from opensolve_pipe.models.project import Project
from opensolve_pipe.services.solver import solve_project
from tests.differential.corpus import items, load
from tests.differential.equipment_check import (
    NO_CURVES,
    G,
    _dump,
    check,
    check_all,
    element_problems,
    network_problems,
    rating_for,
    replaced,
    summarize,
)

SMOKE_FUZZ = (
    [f"fuzz_{s}" for s in range(60)]
    + [f"fuzzfc_{s}" for s in range(10_000, 10_050)]
    + [f"fuzzaf_{s}" for s in range(20_000, 20_050)]
)


def _item(name: str) -> Any:
    return next(spec for n, spec in items() if n == name)


def test_equipment_over_the_reference_cases_unit_networks_and_fuzz_seeds() -> None:
    selection = [t for t in items() if t[0].startswith(("ref_", "unit_")) or t[0] in SMOKE_FUZZ]
    assert len([t for t in selection if t[0].startswith("fuzz")]) == len(SMOKE_FUZZ)
    records = check_all(selection)
    different = [f"{r['name']}: {'; '.join(r['differences'])}" for r in records if r["differences"]]
    assert not different, "\n".join(different)
    outcomes = Counter(r["outcome"] for r in records)
    assert outcomes["load_error"] == outcomes["crash"] == 0, outcomes
    kinds: dict[str, Counter[str]] = {}
    for r in records:
        kinds.setdefault(r["profile"], Counter()).update(r.get("counts", {}))
    for profile in ("ref", "fuzz", "fuzzfc", "fuzzaf"):
        for kind in ("point", "Cv", "Kv"):
            assert kinds[profile][kind] >= 1, (profile, kinds[profile])
        flowing = [r for r in records if r["profile"] == profile and r.get("lossy")]
        assert flowing, profile  # an element whose loss D6 can see
    assert sum(k["no_result"] for k in kinds.values()) >= 1, kinds
    checked = {r["name"]: r for r in records if r["outcome"] == "checked"}
    assert len(checked) >= 40, len(checked)
    assert sum(r.get("reverse", 0) for r in checked.values()) >= 1
    assert "unit_seed2258" in checked  # an element in a floating section (UNDETERMINED_PRESSURE)
    lines = summarize(records)
    assert lines[-1] == "different: 0"
    assert lines[0].startswith("profile projects checked different point Cv Kv")


@pytest.mark.parametrize(
    "name",
    [
        "ref_isolation_valve_cv",
        "ref_isolation_valves_kv_and_k",
        "ref_isolation_valves_crane_default_k",
        "fuzzaf_20014",
    ],
)
def test_a_falsified_law_is_reported(name: str) -> None:
    """Each element's c × 1.21 (a Cv or Kv ÷ 1.1, a rated drop × 1.21) in a network where the
    element's loss matters: its flows and head losses move beyond D6, (b) and (c)."""
    record = check(name, load(_item(name)), scale=1.21)
    assert record["outcome"] == "different", record
    letters = {d[:3] for d in record["differences"]}
    assert {"(b)", "(c)"} <= letters, record["differences"]
    assert check(name, load(_item(name)))["differences"] == []


@pytest.mark.parametrize("name", ["fuzz_25", "fuzz_49", "fuzzaf_20004"])
def test_the_largest_differences_show_a_law_that_d6_does_not(name: str) -> None:
    """Where a valve carries flow but its loss is small (a rated point, a Kv and a Cv here, each
    below 0.01 m), c × 1.21 stays within D6, but the largest differences recorded are many
    orders above those of the element's own law (module docstring)."""
    true = check(name, load(_item(name)))
    false = check(name, load(_item(name)), scale=1.21)
    assert true["outcome"] == false["outcome"] == "checked", (true, false)
    for quantity in ("flow", "head"):
        assert false["largest"][quantity] > 1.0e3 * true["largest"][quantity], (true, false)


def _solved_pair(name: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    project = load(_item(name))
    base = project.model_dump(mode="json", by_alias=True, exclude_unset=True)
    a = _dump(solve_project(project, NO_CURVES))
    data, kinds, _ = replaced(name, base, a)
    b = _dump(solve_project(Project.model_validate(data), NO_CURVES))
    return data, a, b, next(iter(kinds))


def test_a_falsified_result_is_reported() -> None:
    """(d): pressureLoss is ρg × headLoss and pressureDrop the §3.3 identity to round-off; one
    part in 10⁹ off is reported, and so is a static drop one pascal off."""
    data, a, b, eid = _solved_pair("ref_isolation_valves_crane_default_k")
    assert element_problems(data, a, b, eid) == ([], [])
    item = b["equipmentResults"][eid]
    assert item["pressureLoss"] == pytest.approx(b["fluid"]["density"] * G * item["headLoss"])
    off = copy.deepcopy(b)
    off["equipmentResults"][eid]["pressureLoss"] *= 1.0 + 1.0e-9
    (found,), _ = element_problems(data, a, off, eid)
    assert found.startswith(f"(d) {eid}: pressureLoss")
    off = copy.deepcopy(b)
    off["equipmentResults"][eid]["pressureDrop"] += 1.0
    (found,), _ = element_problems(data, a, off, eid)
    assert found.startswith(f"(d) {eid}: pressureDrop")
    # the head loss of the valve beyond D6: (c)
    off = copy.deepcopy(b)
    off["equipmentResults"][eid]["headLoss"] += 0.011 + 0.005 * abs(item["headLoss"])
    listed, _ = element_problems(data, a, off, eid)
    assert any(f.startswith(f"(c) headLoss of {eid}") for f in listed), listed


def test_differences_only_at_zero_flow_are_listed_apart() -> None:
    """(b): a connection whose flow is reported as exactly 0 on a side differs only at zero flow
    (CLAUDE.md D13), and so do the EGL and pressure at its ports; elsewhere, a difference."""
    data, a, b, _ = _solved_pair("ref_isolation_valves_crane_default_k")
    assert network_problems(data, a, b) == ([], [])
    conn = next(k for k, link in a["linkResults"].items() if abs(link["flow"]) > 1.0e-6)
    flowing = copy.deepcopy(b)
    flowing["linkResults"][conn]["flow"] *= 1.01
    found, at_zero = network_problems(data, a, flowing)
    assert [f.split(":")[0] for f in found] == [f"(b) flow of {conn}"]
    assert at_zero == []
    stopped = copy.deepcopy(b)
    stopped["linkResults"][conn]["flow"] = 0.0
    ports = [
        f"{c[side + 'ComponentId']}:{c[side + 'PortId']}"
        for c in data["connections"]
        if c["id"] == conn
        for side in ("from", "to")
    ]
    for key in ports:
        if key in stopped["nodeResults"]:
            stopped["nodeResults"][key]["egl"] += 1.0
    found, at_zero = network_problems(data, a, stopped)
    assert found == []
    assert f"(b) flow of {conn}" in [z.split(":")[0] for z in at_zero]


def test_the_replacement_stands_in_for_the_valve() -> None:
    """A Cv or Kv valve becomes the same Cv or Kv; another one a rated point whose c is the
    valve's K_open/(2gA²) to round-off, with ρ_r in 800-1200 kg/m³; one whose rated drop would
    pass 10⁸ Pa is kept."""
    rng = random.Random("test")
    result = {"kOpen": 0.17, "referenceDiameter": 0.1023}
    cv = {"resistance": {"kind": "Cv", "value": 90.0}}
    assert rating_for(cv, result, rng) == {"kind": "Cv", "value": 90.0}
    kv = {"resistance": {"kind": "Kv", "value": 60.0}}
    assert rating_for(kv, result, rng, scale=4.0) == {"kind": "Kv", "value": 30.0}
    for valve in ({}, {"resistance": {"kind": "K", "value": 0.17}}):
        point = rating_for(valve, result, rng)
        assert point is not None
        assert point["kind"] == "point"
        assert 800.0 <= point["density"] <= 1200.0
        c = point["pressureLoss"] / (point["density"] * G * point["flow"] ** 2)
        area = math.pi * 0.1023**2 / 4
        assert c == pytest.approx(0.17 / (2 * G * area**2), rel=1e-14)
    # ρ_r K/2 > 10⁸ Pa at every ρ_r of the range: K > 2.5·10⁵
    assert rating_for({}, {"kOpen": 2.6e5, "referenceDiameter": 0.01}, rng) is None
    # in a project: the element keeps the valve's id, name, elevation and ports
    name = "ref_isolation_valves_kv_and_k"
    project = load(_item(name))
    base = project.model_dump(mode="json", by_alias=True, exclude_unset=True)
    state = _dump(solve_project(project, NO_CURVES))
    data, kinds, counts = replaced(name, base, state)
    assert counts == Counter({"point": 1, "Kv": 1})
    assert set(kinds.values()) == {"point", "Kv"}
    for valve in (c for c in base["components"] if c["id"] in kinds):
        element = next(c for c in data["components"] if c["id"] == valve["id"])
        assert element["type"] == "equipment"
        for key in ("name", "elevation", "ports"):
            assert element[key] == valve[key]
    assert data["connections"] == base["connections"]
