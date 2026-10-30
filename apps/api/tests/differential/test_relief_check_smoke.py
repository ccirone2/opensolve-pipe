"""Smoke test of the relief-valve corpus check (``relief_check``, proposal pressure-relief-valve.md
§7.4): the reference cases, the unit-test data networks, a few seeds of each fuzz profile and the
corpus projects of each listed class go through the same checks as
``python -m tests.differential.relief_check``, in its three modes, and none may differ. The
selection must reach every placement the check makes (a relief valve at partial lift, beyond full
lift and closed, in every fuzz profile, placed reversed too), the valves it keeps and those
without a result, a relief valve in a floating section, and each class it lists (values different
only at zero flow, which nodes have results, an element at its switch), so that a check that
compared nothing would fail here; and the checks themselves must catch a relief valve whose law
or result was falsified, and the largest differences recorded must show a falsified law where D6
does not. The full corpus run is the command-line tool."""

import copy
import math
import random
from collections import Counter
from collections.abc import Callable
from typing import Any

import pytest

from opensolve_pipe.models.project import Project
from opensolve_pipe.services.solver import solve_project
from tests.differential.corpus import items, load
from tests.differential.equipment_check import NO_CURVES, G, _dump, active_isolation_valves
from tests.differential.relief_check import (
    MARGIN,
    MODES,
    Placed,
    as_a,
    check,
    check_all,
    classify,
    element_problems,
    isolated,
    law_at,
    place_closed,
    place_open,
    relief_json,
    replaced,
    result_problems,
    summarize,
)

SMOKE_FUZZ = (
    [f"fuzz_{s}" for s in range(60)]
    + [f"fuzzfc_{s}" for s in range(10_000, 10_050)]
    + [f"fuzzaf_{s}" for s in range(20_000, 20_050)]
)
LISTED = [
    # (project, mode, the class the full corpus run lists it in; TSD §10.4)
    ("fuzzfc_10917", "band", "zero_flow"),  # a floating loop closed only by the relief valve
    ("fuzz_156", "closed", "zero_flow"),  # the closed relief valve's side closed off in B
    ("fuzz_497", "closed", "nodes"),  # a circulating section floating in B, set in A'
    ("fuzz_1259", "closed", "switch"),  # the relief valve open at its switch, Q ≈ -4e-10
    ("fuzzfc_10169", "band", "switch"),  # FCV8 open in A, closed in B, within Htol
]
"""Corpus projects of each class the check lists, with the class (relief_check docstring)."""
EXTRA = ["fuzz_161", *(name for name, _, _ in LISTED)]
"""Projects outside the seeds: fuzz_161 places a relief valve in a floating section."""


def _item(name: str) -> Any:
    return next(spec for n, spec in items() if n == name)


@pytest.fixture(scope="module")
def records() -> list[dict[str, Any]]:
    names = set(SMOKE_FUZZ) | set(EXTRA)
    selection = [t for t in items() if t[0].startswith(("ref_", "unit_")) or t[0] in names]
    assert len([t for t in selection if t[0].startswith("fuzz")]) == len(names)
    return check_all(selection)


def test_relief_valves_over_the_reference_cases_unit_networks_and_fuzz_seeds(
    records: list[dict[str, Any]],
) -> None:
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
            for state, n in sub.get("states", {}).items():  # B's relief valves
                counted["no_relief_result" if state == "no_result" else state] += n
            for key in ("flowing", "lossy", "floating"):
                counted[key] += sub.get(key, 0)
            counted[sub["outcome"]] += 1
        for profile in ("ref", "fuzz", "fuzzfc", "fuzzaf"):
            assert tally[profile]["replaced"] >= 1, (mode, profile, tally[profile])
            assert tally[profile]["lossy"] >= 1, (mode, profile)  # a loss D6 can see
        total: Counter[str] = sum(tally.values(), Counter())
        assert total["checked"] >= 10, (mode, total)
        if mode == "closed":
            assert total["closed"] >= 20, total
            assert total["no_relief_result"] >= 1, total  # closed off in B (fuzz_156)
            assert total["flowing"] >= 1, total  # one open at its switch (fuzz_1259)
            assert sum(total[k] for k in total if k.startswith("skipped_")) >= 1, total
            continue
        state = "partial_lift" if mode == "band" else "full_lift"
        assert total[state] >= total["replaced"] - 1 >= 10, (mode, total)  # fuzzfc_10917
        assert total["reversed"] >= 1, (mode, total)
        assert total["floating"] >= 1, (mode, total)  # fuzz_161
        assert total["kept_no_flow"] >= 1, (mode, total)
        assert total["kept_margin"] >= 1, (mode, total)
        assert total["no_result"] >= 1, (mode, total)  # a valve without a result in A
        assert total["no_relief_result"] >= 1, (mode, total)  # fuzzfc_10917
    lines = summarize(records)
    assert lines[-1] == "different: 0"
    assert lines[:2] == [
        "mode band",
        "profile projects checked different replaced reversed partial_lift full_lift closed"
        " no_relief_result flowing lossy floating kept_no_flow kept_margin kept_bounds no_result"
        " skipped not_converged at_zero_flow at_switch no_valve none_replaced topology_error"
        " load_error crash",
    ]


@pytest.mark.parametrize(("name", "mode", "listed"), LISTED, ids=[f"{n}-{m}" for n, m, _ in LISTED])
def test_the_known_classes_are_listed_not_different(
    records: list[dict[str, Any]], name: str, mode: str, listed: str
) -> None:
    """Each project the full corpus run lists stays in its class (CLAUDE.md D9, D13): values
    different only at zero flow, which nodes have results, or an element at its switch."""
    (record,) = (r for r in records if r["name"] == name)
    sub = record["modes"][mode]
    assert sub["outcome"] == "checked", sub
    assert not sub["differences"], sub["differences"]
    nodes = [t for t in sub["atZeroFlow"] if t.startswith("which nodes have results")]
    if listed == "switch":
        assert sub["atSwitch"], sub
        assert sub["atSwitch"][0].startswith("at its switch: "), sub
    elif listed == "nodes":
        assert nodes, sub
    else:
        assert sub["atZeroFlow"], sub
        assert not nodes, sub
        assert not sub["atSwitch"], sub


@pytest.mark.parametrize(
    ("name", "mode", "scale", "letters"),
    [
        ("ref_isolation_valve_cv", "band", 1.21, {"(b)", "(c)"}),
        ("ref_isolation_valves_crane_default_k", "band", 1.21, {"(b)", "(c)"}),
        ("fuzzaf_20014", "band", 1.21, {"(b)", "(c)"}),
        ("ref_isolation_valve_cv", "full", 1.21, {"(b)", "(c)"}),
        ("ref_isolation_valves_kv_and_k", "full", 1.21, {"(b)", "(c)"}),
        ("fuzzaf_20036", "full", 1.21, {"(b)", "(c)"}),
        ("ref_isolation_valve_cv", "closed", 0.3, {"(c)"}),
        ("fuzz_21", "closed", 0.3, {"(b)", "(c)"}),
        ("fuzzfc_10029", "closed", 0.3, {"(b)", "(c)"}),
    ],
)
def test_a_falsified_law_is_reported(name: str, mode: str, scale: float, letters: set[str]) -> None:
    """Each relief valve's C × 1.21 at partial or beyond full lift, or its set × 0.3 where it
    should stay closed, in a network where the relief valve's loss matters: its flows and head
    losses move beyond D6, (b) and (c); B's own result still follows its (falsified) law, so (d)
    and (e) do not fire."""
    record = check(name, load(_item(name)), (mode,), scale=scale)
    assert record["outcome"] == "different", record
    found = {d.split(" ", 2)[1] for d in record["differences"]}
    assert letters <= found, record["differences"]
    assert not found & {"(d)", "(e)"}, record["differences"]
    assert check(name, load(_item(name)), (mode,))["differences"] == []


NOISE = {"flow": 2.0e-9, "head": 1.0e-5}
"""The largest differences the relief valve's own law gives over the whole corpus in modes
``band`` and ``full``, over the projects with no listed class, rounded up: 1.05e-9 of the largest
flow (fuzzaf_20730, full) and 4.47e-6 m (fuzzaf_20938, whose heads reach 4,600 m: the solver's
flow tolerance there; TSD §10.4). They come from round-off and the solver's stop tolerances, so
they differ between CPUs: one run's own differences are no fixed yardstick (equipment_check's and
orifice_check's NOISE)."""


@pytest.mark.parametrize(
    ("name", "mode", "quantities"),
    [
        ("fuzz_25", "full", ("flow", "head")),
        ("fuzz_49", "full", ("flow", "head")),
        ("fuzzaf_20018", "full", ("flow", "head")),
        ("fuzzfc_10011", "full", ("head",)),
        ("fuzzaf_20004", "band", ("head",)),
    ],
)
def test_the_largest_differences_show_a_law_that_d6_does_not(
    name: str, mode: str, quantities: tuple[str, ...]
) -> None:
    """Where a relief valve carries flow but its loss is small (below 0.01 m), C × 1.21 stays
    within D6, but the largest differences recorded rise more than ten times above everything the
    relief valve's own law gives over the corpus (``NOISE``), so the corpus run's summary shows
    it. In fuzzfc_10011 and fuzzaf_20004 the relief valve's flow is held by a flow control or an
    assigned flow whatever its loss: only the heads can show the law there."""
    true = check(name, load(_item(name)), (mode,))
    false = check(name, load(_item(name)), (mode,), scale=1.21)
    assert true["outcome"] == false["outcome"] == "checked", (true, false)
    t, f = true["modes"][mode], false["modes"][mode]
    assert t["lossy"] == 0 < t["flowing"], t
    assert not t["listed"], t
    for quantity in ("flow", "head"):
        assert t["largest"][quantity] <= NOISE[quantity], (t, f)
    for quantity in quantities:
        assert f["largest"][quantity] > 10.0 * NOISE[quantity], (t, f)


def _solved(name: str, mode: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Any]:
    """(B's project, A or A', B, the placed relief valves) of a project in a mode."""
    project = load(_item(name))
    base = project.model_dump(mode="json", by_alias=True, exclude_unset=True)
    a = _dump(solve_project(project, NO_CURVES))
    closed = None
    if mode == "closed":
        vid = next(v["id"] for v in active_isolation_valves(base) if v["id"] in a["valveResults"])
        closed = _dump(solve_project(Project.model_validate(isolated(base, vid)), NO_CURVES))
    data, placed, _ = replaced(mode, name, base, a, closed)
    b = _dump(solve_project(Project.model_validate(data), NO_CURVES))
    return data, (closed if closed is not None else a), b, placed


@pytest.mark.parametrize("mode", MODES)
def test_a_falsified_result_is_reported(mode: str) -> None:
    """(d) and (e): the total-pressure difference, static drop and port pressures follow from the
    heads and the law's every value from the placed valve at the reported flow, to round-off; one
    part in 10⁹ off, a pascal off, or another word, is reported; (c) a head loss beyond D6."""
    data, a, b, placed = _solved("ref_isolation_valves_crane_default_k", mode)
    rid = next(iter(placed))
    p = placed[rid]
    assert result_problems(data, b, rid, p) == []
    assert element_problems(mode, data, a, b, rid, p) == ([], [])
    item = b["reliefValveResults"][rid]
    nudged: list[tuple[str, Callable[[Any], Any], str]] = [
        ("totalPressureDifference", lambda x: x + 1.0, "(d)"),
        ("pressureDrop", lambda x: x + 1.0, "(d)"),
        ("inletPressure", lambda x: x + 1.0, "(d)"),
        ("backPressure", lambda x: x + 1.0, "(d)"),
        ("setPressure", lambda x: x * (1.0 + 1.0e-9), "(e)"),
        ("overpressure", lambda x: x * (1.0 + 1.0e-9), "(e)"),
        ("overpressureSource", lambda x: "asme_default", "(e)"),
        ("fullLiftPressureDifference", lambda x: x * (1.0 + 1.0e-9), "(e)"),
        ("fullLiftFlow", lambda x: x * (1.0 + 1.0e-9), "(e)"),
        ("setRatio", lambda x: x * (1.0 + 1.0e-9), "(e)"),
        ("capacity", lambda x: {**x, "area": x["area"] * (1.0 + 1.0e-9)}, "(e)"),
    ]
    if mode == "closed":
        nudged += [
            ("state", lambda x: "partial_lift", "(e)"),
            ("reynoldsNumber", lambda x: 1.0, "(e)"),
        ]
    else:
        nudged += [
            ("lift", lambda x: x * (1.0 + 1.0e-9) if x < 1.0 else 0.999, "(e)"),
            ("flowRatio", lambda x: x * (1.0 + 1.0e-9), "(e)"),
            ("reynoldsNumber", lambda x: x * (1.0 + 1.0e-9), "(e)"),
            ("headLoss", lambda x: x + 2.0e-6, "(e)"),
            ("state", lambda x: "closed", "(e)"),
        ]
    for field, change, letter in nudged:
        off = copy.deepcopy(b)
        off["reliefValveResults"][rid][field] = change(item[field])
        found = result_problems(data, off, rid, p)
        assert any(f.startswith(f"{letter} {rid}: {field}") for f in found), (field, found)
    if mode != "closed":  # the head loss of the valve beyond D6: (c)
        off = copy.deepcopy(b)
        off["reliefValveResults"][rid]["headLoss"] += 0.011 + 0.005 * abs(item["headLoss"])
        listed, _ = element_problems(mode, data, a, off, rid, p)
        assert any(f.startswith(f"(c) headLoss of {rid}") for f in listed), listed
    else:  # an open relief valve where A' has it closed: (c)
        off = copy.deepcopy(b)
        off["reliefValveResults"][rid]["flow"] = 1.0e-3
        listed, _ = element_problems(mode, data, a, off, rid, p)
        assert any(f.startswith(f"(c) flow of {rid}") for f in listed), listed
    # a reverse flow beyond Qtol, which cvstatus closes: (e)
    off = copy.deepcopy(b)
    off["reliefValveResults"][rid]["flow"] = -2.0e-8
    found = result_problems(data, off, rid, p)
    assert any(f.startswith(f"(e) {rid}: reverse flow") for f in found), found


def test_the_law_at_a_flow_is_the_relief_law() -> None:
    """``law_at`` (an independent solve of the band) satisfies the law's definitions: Q = x·C·
    √(2Δp/ρ) with x = (Δp − Δp_s)/(op·Δp_s) in the band, x = 1 and Δp = ρQ²/(2C²) from Q_f on,
    continuous at Q_f; closed at no flow (test inputs: proposal §7.1's network M valve, API 526
    F at Kd 0.65, set 500 kPa, op 0.1)."""
    placed = Placed(5.0e5, 0.1, 0.65, 1.9806412e-4)
    rho, c = 998.0, placed.c_area
    q_full = c * math.sqrt(2.0 * placed.full_lift_pressure / rho)
    assert q_full == pytest.approx(0.004274154702, rel=1e-9)  # proposal §7.1, network M
    for q in (1.0e-9, 1.0e-4, 0.0022212108023477624, 0.004, q_full * (1.0 - 1.0e-12)):
        point = law_at(placed, rho, q)
        assert point.state == "partial_lift"
        x = (point.pressure_difference - 5.0e5) / (0.1 * 5.0e5)
        assert point.lift == pytest.approx(x, rel=1e-9, abs=1e-15)
        assert q == pytest.approx(x * c * math.sqrt(2.0 * point.pressure_difference / rho))
    # C2's partial lift (proposal §7.1): x 0.5311270926 at Q 0.002221210802348
    assert law_at(placed, rho, 0.002221210802347762).lift == pytest.approx(0.5311270926, rel=1e-9)
    for q in (q_full, 0.0047):
        point = law_at(placed, rho, q)
        assert (point.state, point.lift) == ("full_lift", 1.0)
        assert point.pressure_difference == pytest.approx(rho * q * q / (2.0 * c * c), rel=1e-15)
    assert law_at(placed, rho, q_full).pressure_difference == pytest.approx(
        placed.full_lift_pressure, rel=1e-14
    )
    assert law_at(placed, rho, 0.0).state == "closed"


def test_the_placement_stands_in_for_the_valve() -> None:
    """A placed relief valve's law gives A's valve flow at A's total-pressure difference: at lift
    x in mode ``band``, at Δp_A/(k Δp_f) beyond full lift in mode ``full``; a reverse flow puts
    its inlet at the valve's outlet port (port ids swapped in the component and the connections,
    node results read back by A's ids); a valve with no flow, or with a difference too close to
    the set, stays a valve; and mode ``closed`` sets it above A''s difference across the closed
    valve."""
    rho = 998.2  # a test input
    valve = {
        "type": "valve",
        "valveType": "gate",
        "id": "IV1",
        "name": "IV1",
        "elevation": 0.0,
        "ports": [
            {"id": "inlet", "nominalSize": 0.1016, "elevation": 0.5},
            {"id": "outlet", "nominalSize": 0.1016},
        ],
    }
    project = {"components": [valve], "connections": []}
    dz = 0.5  # z_in − z_out
    for mode in ("band", "full"):
        for flow, head in ((0.02, 30.0), (-0.02, -30.0)):
            result = {"flow": flow, "headLoss": head}
            placed, why = place_open(mode, project, valve, result, rho, random.Random(mode))
            assert placed is not None, why
            assert placed.reversed is (flow < 0.0)
            z = dz if flow > 0.0 else -dz  # z_up − z_down
            dp = rho * G * (abs(head) - z)
            point = law_at(placed, rho, abs(flow))
            assert point.pressure_difference == pytest.approx(dp, rel=1e-12)
            assert point.state == ("partial_lift" if mode == "band" else "full_lift")
            assert 0.05 <= placed.overpressure <= 0.5
            assert 0.6 <= placed.coefficient <= 0.9
            if mode == "full":
                ratio = dp / placed.full_lift_pressure
                assert 1.05 <= ratio <= 2.0
            else:
                assert 0.1 <= point.lift <= 0.9
            relief = relief_json(valve, placed)
            ports = {p["id"]: p for p in relief["ports"]}
            assert ports["inlet"].get("elevation") == (0.5 if flow > 0 else None)
            assert relief["capacity"]["kind"] == "certified"
    still = {"flow": 1.0e-10, "headLoss": 1.0}
    assert place_open("band", project, valve, still, rho, random.Random(0)) == (None, "no_flow")
    small = {"flow": 0.02, "headLoss": dz + 1.0e-4}  # Δp_A − Δp_s below MARGIN ρg
    assert place_open("band", project, valve, small, rho, random.Random(0)) == (
        None,
        "margin",
    )
    huge = {"flow": 100.0, "headLoss": dz + 0.1}  # C/K beyond 78.54 m² for any K ≤ 0.9
    assert place_open("full", project, valve, huge, rho, random.Random(0)) == (None, "bounds")
    # mode closed: above A''s difference by at least 5 % and MARGIN ρg
    closed = {
        "nodeResults": {"IV1:inlet": {"egl": 40.0}, "IV1:outlet": {"egl": 20.0}},
        "flags": [],
    }
    result = {"referenceDiameter": 0.1023, "kOpen": 0.17}
    placed, why = place_closed(project, valve, result, closed, rho, random.Random(1))
    assert placed is not None, why
    dp = rho * G * (40.0 - 20.0 - dz)
    assert placed.set_pressure >= 1.05 * dp + MARGIN * rho * G
    assert placed.c_area == pytest.approx(math.pi * 0.1023**2 / 4 / math.sqrt(0.17), rel=1e-14)
    floating = {**closed, "flags": [{"code": "UNDETERMINED_PRESSURE"}]}
    assert place_closed(project, valve, result, floating, rho, random.Random(1)) == (
        None,
        "floating",
    )
    headless = {"nodeResults": {"IV1:inlet": {"egl": 40.0}}, "flags": []}
    assert place_closed(project, valve, result, headless, rho, random.Random(1)) == (
        None,
        "no_head",
    )
    # in a project: the reversed relief valve keeps the valve's id, name, elevation and ports
    name = "ref_isolation_valves_crane_default_k"
    p = load(_item(name))
    base = p.model_dump(mode="json", by_alias=True, exclude_unset=True)
    a = _dump(solve_project(p, NO_CURVES))
    data, placed_by_id, counts = replaced("band", name, base, a)
    assert counts["replaced"] == len(placed_by_id) >= 2, counts
    for vid, placement in placed_by_id.items():
        before = next(c for c in base["components"] if c["id"] == vid)
        after = next(c for c in data["components"] if c["id"] == vid)
        assert after["type"] == "relief_valve"
        for key in ("name", "elevation"):
            assert after[key] == before[key]
        assert {q["id"] for q in after["ports"]} == {"inlet", "outlet"}
        assert placement.reversed is (a["valveResults"][vid]["flow"] < 0.0)
    b = _dump(solve_project(Project.model_validate(data), NO_CURVES))
    mapped = as_a(b, placed_by_id)
    assert set(mapped["nodeResults"]) == set(a["nodeResults"])


def test_the_classes_are_told_apart() -> None:
    """``classify``: node values one side lacks alone are 'which nodes have results'; flows (and
    such values) with an element at its switch are 'at a switch'; a head that differs, or flows
    with no element at its switch, are differences."""
    presence = "(b) egl at PU3:discharge: 14.5 against None"
    flow = "(b) flow of C4: 6.16e-05 against 6.34e-05"
    relief = "(c) flow of IV4: A' 0.0, relief -4.4e-10"
    head = "(b) egl at T1:branch: 10.08 against 25.09"
    assert classify([presence], []) == ([], [f"which nodes have results: {presence}"], [])
    assert classify([flow, relief, presence], ["FCV8"]) == (
        [],
        [],
        ["at its switch: FCV8", flow, relief, presence],
    )
    assert classify([flow], []) == ([flow], [], [])
    assert classify([flow, head], ["FCV8"]) == ([flow, head], [], [])
    assert classify([], ["FCV8"]) == ([], [], [])
