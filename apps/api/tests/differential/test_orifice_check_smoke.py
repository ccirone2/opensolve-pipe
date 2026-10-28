"""Smoke test of the orifice-plate corpus check (``orifice_check``, proposal orifice-plate.md
§7.4): the reference cases, the unit-test data networks and a few seeds of each fuzz profile go
through the same checks as ``python -m tests.differential.orifice_check``, in both modes, and
none may differ. The selection must reach every replacement the check makes (a plate with an
entered C, and on ISO 5167-2's C one with each tap set, in every fuzz profile), a valve kept and
one without a result, a plate in reverse flow, one held below ISO's lowest Reynolds number, one
whose C varies with its own Reynolds number where D6 can see its loss, and one in a floating
section, so that a check that compared nothing would fail here; and the checks themselves must
catch a plate whose law or result was falsified, and the largest differences recorded must show
a falsified law where D6 does not. The full corpus run is the command-line tool."""

import copy
import math
import random
from collections import Counter
from typing import Any

import pytest
from fluids.flow_meter import discharge_coefficient_to_K

from opensolve_pipe.models.project import Project
from opensolve_pipe.services.solver import solve_project
from tests.differential.corpus import items, load
from tests.differential.equipment_check import NO_CURVES, G, _dump
from tests.differential.orifice_check import (
    BETA_MAX,
    MODES,
    check,
    check_all,
    coefficient_problems,
    element_problems,
    entered_beta,
    iso_beta,
    iso_loss_c,
    plate_for,
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


def test_orifices_over_the_reference_cases_unit_networks_and_fuzz_seeds() -> None:
    selection = [t for t in items() if t[0].startswith(("ref_", "unit_")) or t[0] in SMOKE_FUZZ]
    assert len([t for t in selection if t[0].startswith("fuzz")]) == len(SMOKE_FUZZ)
    records = check_all(selection)
    different = [f"{r['name']}: {'; '.join(r['differences'])}" for r in records if r["differences"]]
    assert not different, "\n".join(different)
    outcomes = Counter(r["outcome"] for r in records)
    assert outcomes["load_error"] == outcomes["crash"] == 0, outcomes
    for mode in MODES:
        tally: dict[str, Counter[str]] = {}
        for r in records:
            sub = r["modes"].get(mode)
            if sub is None:
                continue
            counted = tally.setdefault(r["profile"], Counter())
            counted.update(sub["counts"])
            for key in ("reverse", "flowing", "held", "lossy", "varying"):
                counted[key] += sub.get(key, 0)
            counted[sub["outcome"]] += 1
        for profile in ("ref", "fuzz", "fuzzfc", "fuzzaf"):
            assert tally[profile]["replaced"] >= 1, (mode, profile, tally[profile])
            assert tally[profile]["lossy"] >= 1, (mode, profile)  # a loss D6 can see
        total: Counter[str] = sum(tally.values(), Counter())
        assert total["checked"] >= 35, (mode, total)
        assert total["kept"] >= 1, (mode, total)
        assert total["no_result"] >= 1, (mode, total)
        assert total["reverse"] >= 1, (mode, total)
        if mode == "iso":
            for taps in ("corner", "flange", "d_and_d_2"):
                assert total[f"taps_{taps}"] >= 1, (taps, total)
            assert total["replaced"] > total["tapped"]  # and plates without taps
            assert total["held"] >= 1, total  # C held at Re_lo (or zero flow)
            assert total["varying"] >= 1, total  # C at its own Re, where D6 sees the loss
        else:
            assert total["tapped"] == total["held"] == total["varying"] == 0, total
        floating = next(r for r in records if r["name"] == "unit_seed2258")  # UNDETERMINED_PRESSURE
        assert floating["modes"][mode]["outcome"] == "checked", floating
    lines = summarize(records)
    assert lines[-1] == "different: 0"
    assert lines[:2] == [
        "mode entered",
        "profile projects checked different replaced flowing"
        " lossy held varying tapped untapped kept no_result not_converged"
        " at_zero_flow reverse no_valve none_replaced topology_error"
        " load_error crash",
    ]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    "name",
    [
        "ref_isolation_valve_cv",
        "ref_isolation_valves_kv_and_k",
        "ref_isolation_valves_crane_default_k",
        "fuzzaf_20014",
    ],
)
def test_a_falsified_law_is_reported(name: str, mode: str) -> None:
    """Each plate's K × 1.21 at its valve's flow in a network where the plate's loss matters:
    its flows and head losses move beyond D6, (b) and (c)."""
    record = check(name, load(_item(name)), (mode,), scale=1.21)
    assert record["outcome"] == "different", record
    letters = {d.split(" ", 1)[1][:3] for d in record["differences"]}
    assert {"(b)", "(c)"} <= letters, record["differences"]
    assert check(name, load(_item(name)), (mode,))["differences"] == []


NOISE = {"flow": 1.0e-9, "head": 1.0e-5}
"""The largest differences the plate's own law gives over the whole corpus, in either mode,
rounded up: 9.3e-10 of the largest flow and 6.7e-6 m (fuzzaf_20938, whose heads reach 4,600 m:
the solver's flow tolerance of 10⁻⁹ there; TSD §10.4). They come from round-off and the solver's
stop tolerances, so they differ between CPUs: one run's own differences are no fixed yardstick
(equipment_check's NOISE)."""


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    ("name", "quantities"),
    [
        ("fuzz_25", ("flow", "head")),
        ("fuzz_50", ("flow", "head")),
        ("fuzzaf_20018", ("flow", "head")),
        ("fuzzfc_10011", ("head",)),
    ],
)
def test_the_largest_differences_show_a_law_that_d6_does_not(
    name: str, quantities: tuple[str, ...], mode: str
) -> None:
    """Where a valve carries flow but its loss is small (below 0.01 m), K × 1.21 stays within
    D6, but the largest differences recorded rise more than ten times above everything the
    plate's own law gives over the corpus (``NOISE``), so the corpus run's summary shows it. In
    fuzzfc_10011 the valve's flow is held by a flow control whatever its loss: only the heads
    can show the law there."""
    true = check(name, load(_item(name)), (mode,))
    false = check(name, load(_item(name)), (mode,), scale=1.21)
    assert true["outcome"] == false["outcome"] == "checked", (true, false)
    t, f = true["modes"][mode], false["modes"][mode]
    assert t["lossy"] == 0 < t["flowing"], t
    for quantity in ("flow", "head"):
        assert t["largest"][quantity] <= NOISE[quantity], (t, f)
    for quantity in quantities:
        assert f["largest"][quantity] > 10.0 * NOISE[quantity], (t, f)


def _solved_pair(
    name: str, mode: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str, Any]:
    project = load(_item(name))
    base = project.model_dump(mode="json", by_alias=True, exclude_unset=True)
    a = _dump(solve_project(project, NO_CURVES))
    data, plates, _ = replaced(name, base, a, mode)
    b = _dump(solve_project(Project.model_validate(data), NO_CURVES))
    pid = next(p for p in plates if b["orificeResults"][p]["flow"] != 0.0)
    return data, a, b, pid, plates[pid]


@pytest.mark.parametrize("mode", MODES)
def test_a_falsified_result_is_reported(mode: str) -> None:
    """(d) and (e): pressureLoss is ρg × headLoss, pressureDrop the static-drop identity and
    every coefficient the one fluids and §1.1 give at the reported flow, to round-off; one part
    in 10⁹ off, a pascal off, or a field that should be null and is not, is reported."""
    data, a, b, pid, plate = _solved_pair("ref_isolation_valves_crane_default_k", mode)
    assert element_problems(data, a, b, pid) == ([], [])
    assert coefficient_problems(data, b, pid, plate) == []
    item = b["orificeResults"][pid]
    assert item["pressureLoss"] == pytest.approx(b["fluid"]["density"] * G * item["headLoss"])
    for field, change, letter in (
        ("pressureLoss", lambda x: x * (1.0 + 1.0e-9), "(d)"),
        ("pressureDrop", lambda x: x + 1.0, "(d)"),
        ("dischargeCoefficient", lambda x: x * (1.0 + 1.0e-9), "(e)"),
        ("lossCoefficient", lambda x: x * (1.0 + 1.0e-9), "(e)"),
        ("reynoldsNumber", lambda x: x * (1.0 + 1.0e-9), "(e)"),
        ("beta", lambda x: x * (1.0 + 1.0e-9), "(e)"),
        ("pipeDiameter", lambda x: x * (1.0 + 1.0e-9), "(e)"),
        ("venaContractaPressure", lambda x: x + 1.0, "(e)"),
        ("headLoss", lambda x: x + 2.0e-6, "(e)"),
        ("tapCoefficientRatio", lambda x: 1.0, "(e)"),
        ("coefficientSource", lambda x: "entered" if x != "entered" else "iso_5167_2", "(e)"),
    ):
        off = copy.deepcopy(b)
        off["orificeResults"][pid][field] = change(item[field])
        found = element_problems(data, a, off, pid)[0] + coefficient_problems(data, off, pid, plate)
        assert any(f.startswith(f"{letter} {pid}: {field}") for f in found), (field, found)
    # a value where there should be none (no taps, or an entered C), or one part in 10⁹ off
    for field in ("differentialPressure", "meterDischargeCoefficient", "coefficientReynoldsNumber"):
        off = copy.deepcopy(b)
        value = item[field]
        off["orificeResults"][pid][field] = 1.0 if value is None else value * (1.0 + 1.0e-9)
        found = coefficient_problems(data, off, pid, plate)
        assert any(f.startswith(f"(e) {pid}: {field}") for f in found), (field, found)
    # the head loss of the valve beyond D6: (c)
    off = copy.deepcopy(b)
    off["orificeResults"][pid]["headLoss"] += 0.011 + 0.005 * abs(item["headLoss"])
    listed, _ = element_problems(data, a, off, pid)
    assert any(f.startswith(f"(c) headLoss of {pid}") for f in listed), listed


def test_the_replacement_stands_in_for_the_valve() -> None:
    """An entered C (0.6-0.65, no taps) gets the bore whose K is the valve's K_open exactly
    (decision 4's relation inverted); ISO 5167-2's C gets the bore whose K at the valve's flow,
    with C at D and D/2 tappings and held below Re_lo, is K_open; a K the plate cannot reach at
    β 0.95 keeps the valve; a drawn tap set decision 17 refuses is dropped; and in a project the
    plate keeps the valve's id, name, elevation and ports."""
    rng = random.Random("test")
    water = {"density": 998.2, "dynamicViscosity": 1.0016e-3}  # test inputs
    result = {"kOpen": 0.17, "referenceDiameter": 0.1023, "flow": 0.02}
    plate, note = plate_for("entered", result, water, rng)
    assert plate is not None
    assert (note, plate.taps) == ("", None)
    assert plate.entered is not None
    assert 0.6 <= plate.entered <= 0.65
    k = discharge_coefficient_to_K(0.1023, plate.d_bore, plate.entered)
    assert k == pytest.approx(0.17, rel=1e-12)
    assert plate.d_bore == pytest.approx(entered_beta(0.17, plate.entered) * 0.1023, rel=1e-15)
    for flow in (0.02, 1.0e-6, 0.0):  # turbulent; held at Re_lo; zero flow, held too
        r = {**result, "flow": flow}
        plate, _ = plate_for("iso", r, water, random.Random(f"iso{flow}"))
        assert plate is not None
        assert plate.entered is None
        beta = plate.d_bore / 0.1023
        re_d = 4.0 * 998.2 * flow / (math.pi * 0.1023 * 1.0016e-3)
        c = iso_loss_c(0.1023, beta, 998.2, 1.0016e-3, re_d)
        assert discharge_coefficient_to_K(0.1023, plate.d_bore, c) == pytest.approx(0.17, rel=1e-12)
    # K at β 0.95 is 0.058-0.077 with C 0.6-0.65, and 0.031-0.042 on ISO 5167-2's C (about 0.74
    # there): a K below it keeps the valve
    small = {**result, "kOpen": 0.05}
    assert plate_for("entered", small, water, rng) == (None, "")
    assert plate_for("iso", small, water, rng)[0] is not None
    smaller = {**result, "kOpen": 0.02}
    assert plate_for("iso", smaller, water, rng) == (None, "")
    assert iso_beta(0.02, 0.1023, 998.2, 1.0016e-3, 1.0e5) is None
    assert entered_beta(0.08, 0.6) < BETA_MAX < entered_beta(0.07, 0.6)
    # flange taps on a 15.8 mm pipe at β 0.94: eq. (4) at the taps could exceed 1 (decision 17)
    tight = {"kOpen": 0.06, "referenceDiameter": 0.0158, "flow": 1.0e-4}
    rng = next(
        random.Random(s)
        for s in range(1000)
        if random.Random(s).choice((None, "corner", "flange", "d_and_d_2")) == "flange"
    )
    plate, note = plate_for("iso", tight, water, rng)
    assert plate is not None
    assert plate.d_bore / 0.0158 > 0.93
    assert (plate.taps, note) == (None, "untapped")
    # in a project: the plate keeps the valve's id, name, elevation and ports
    name = "ref_isolation_valves_kv_and_k"
    project = load(_item(name))
    base = project.model_dump(mode="json", by_alias=True, exclude_unset=True)
    state = _dump(solve_project(project, NO_CURVES))
    for mode in MODES:
        data, plates, counts = replaced(name, base, state, mode)
        assert counts["replaced"] == len(plates) == 2, counts
        for valve in (c for c in base["components"] if c["id"] in plates):
            plate_json = next(c for c in data["components"] if c["id"] == valve["id"])
            assert plate_json["type"] == "orifice"
            for key in ("name", "elevation", "ports"):
                assert plate_json[key] == valve[key]
            assert (
                plates[valve["id"]].d_pipe
                == state["valveResults"][valve["id"]]["referenceDiameter"]
            )
        assert data["connections"] == base["connections"]
