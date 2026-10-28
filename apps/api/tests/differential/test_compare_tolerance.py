"""Unit checks of the corpus tools' options for change set C1 of proposal
vfd-slice2-discharge-pressure.md (§1.2 C0, §2.7, §9.9): ``compare --within-tolerance`` (and
``--fixed-point``, ``--group``) and ``corpus --solver-options``. Each tolerance is tested just
inside and just outside, with the tolerances written out here from §2.7's table and criterion 7,
not taken from compare.py; the exact mode's output is pinned to that of compare.py before these
options (commit d78a8ef) on an example. Fast; no solve but one small reference case.
"""

import copy
import json
import math
from pathlib import Path
from typing import Any

import pytest

from opensolve_pipe.models.project import Project
from tests.differential import compare, corpus

API_ROOT = Path(__file__).resolve().parents[2]
G = 9.80665  # standard gravity, m/s² (3rd CGPM, 1901), as every trace states
RHO = 998.0  # kg/m³, a test input
Q_MAX = 0.1  # m³/s, the largest flow of the example below
INSIDE, OUTSIDE = 0.99, 1.01  # multiples of a tolerance


def solved() -> dict[str, Any]:
    """A small dump with one value of each quantity (random test inputs, not a solve)."""
    return {
        "converged": True,
        "methodVersion": "1.1.0",
        "timestamp": "2026-10-24T00:00:00Z",
        "atmosphericPressure": 101325.0,
        "fluid": {"name": "water", "density": RHO, "dynamicViscosity": 1.0e-3},
        "linkResults": {
            "C1": {
                "flow": Q_MAX,
                "velocity": 12.166,
                "headLoss": 2.5,
                "reynoldsNumber": 1.2e6,
                "frictionFactor": 0.0185,
                "flowRegime": "turbulent",
                "segments": [{"index": 0, "velocity": 12.166, "headLoss": 2.5}],
                "fittings": [{"index": 0, "quantity": 2, "k": 0.3, "headLoss": 0.1}],
            },
            "C2": {"flow": 0.05, "velocity": 6.083, "headLoss": 0.7, "flowRegime": "turbulent"},
            "C3": {"flow": 2.0e-11, "velocity": 2.4e-9, "headLoss": 0.0, "flowRegime": "laminar"},
        },
        "nodeResults": {
            "P1:discharge": {
                "egl": 52.0,
                "hgl": 44.5,
                "pressure": 2.0e5,
                "absolutePressure": 3.01325e5,
                "velocity": 12.166,
                "elevation": 1.0,
            }
        },
        "pumpResults": {
            "P1": {
                "status": "running",
                "speed": 0.8,
                "operatingFlow": Q_MAX,
                "operatingHead": 30.0,
                "hydraulicPower": 29360.0,
                "curve": [{"flow": 0.0, "head": 40.0}, {"flow": 0.12, "head": 20.0}],
                "systemCurve": [{"flow": 0.0, "head": 10.0}, {"flow": 0.12, "head": 1.49e8}],
            }
        },
        "valveResults": {"V1": {"state": "active", "flow": 0.05, "kEffective": 12.0}},
        "branchResults": {
            "T1": {
                "portFlows": {"run_inlet": 0.06, "run_outlet": -0.05, "branch": -0.01},
                "kFactors": {"run_outlet": 0.04, "branch": 1.2},
                "pathHeadLosses": {"run_outlet": 0.02, "branch": 0.3},
            }
        },
        "boundaryResults": {
            "R1": {"type": "reservoir", "egl": 60.0, "outflow": Q_MAX, "portOutflows": {"p": Q_MAX}}
        },
        "flags": [
            {
                "code": "PUMP_OUTSIDE_CURVE",
                "componentId": "P1",
                "connectionId": None,
                "portId": None,
                "message": "pump 'P1' runs at 0.1 m³/s, beyond its curve's 0.08 m³/s",
                "details": {"headRise": 30.0, "flow": Q_MAX, "speed": 0.8, "step": 0.25},
            }
        ],
        "convergence": {"innerIterations": 7, "message": "converged: 7 Newton iterations"},
        "trace": {
            "elements": {
                "C1": {
                    "inputs": [
                        {"name": "Pipe 1 inner diameter D", "value": 0.1023, "unit": "m"},
                        {"name": "Status", "value": "active", "unit": ""},
                    ],
                    "intermediates": [
                        {"name": "Flow Q", "value": Q_MAX, "unit": "m³/s"},
                        {"name": "Head loss Δh = EGL_from − EGL_to", "value": 2.5, "unit": "m"},
                        {"name": "Inlet static pressure p_in", "value": 2.0e5, "unit": "Pa(g)"},
                        {
                            "name": "Static pressure drop Δp",
                            "value": 1.0e4,
                            "unit": "Pa (difference)",
                        },
                        {"name": "Speed it runs at s", "value": 0.8, "unit": ""},
                        {"name": "Pipe 1 Reynolds number Re", "value": 1.2e6, "unit": ""},
                        {"name": "Fluid dynamic viscosity μ", "value": 1.0e-3, "unit": "Pa·s"},
                    ],
                    "notes": ["Pipe 1: turbulent, Re = 1.2e+06 ≥ 4000: Colebrook."],
                },
                "PRV1": {
                    "inputs": [
                        {"name": "Valve type", "value": "prv", "unit": ""},
                        {"name": "Status", "value": "active", "unit": ""},
                    ],
                    "intermediates": [],
                    "notes": [],
                },
            },
            "methods": {"methodVersion": "1.1.0", "sections": [{"items": ["a", "b"]}]},
        },
    }


def at(doc: Any, path: str) -> Any:
    for seg in path.split("."):
        doc = doc[int(seg)] if isinstance(doc, list) else doc[seg]
    return doc


def put(doc: Any, path: str, value: Any) -> dict[str, Any]:
    """A copy of doc with the value at path ('.'-separated keys and indices) replaced."""
    out: dict[str, Any] = copy.deepcopy(doc)
    *parents, last = path.split(".")
    target: Any = at(out, ".".join(parents)) if parents else out
    target[int(last) if isinstance(target, list) else last] = value
    return out


def judged(a: Any, b: Any, tolerances: compare.Tolerances) -> list[compare.Difference]:
    out: list[compare.Difference] = []
    compare.walk(a, b, "", out, (), [], {}, compare.Judge(a, b, tolerances).leaf)
    return out


PRESSURE_TOL = RHO * G * 1.0e-6  # Pa: ρg·10⁻⁶ m
FLOW_TOL = 1.0e-8 * Q_MAX + 1.0e-14  # m³/s

# (path, quantity, tolerance at the path's value), §2.7's table at default settings
DEFAULT_CASES = [
    ("linkResults.C2.flow", "flow", FLOW_TOL),
    ("valveResults.V1.flow", "flow", FLOW_TOL),
    ("pumpResults.P1.operatingFlow", "flow", FLOW_TOL),
    ("branchResults.T1.portFlows.branch", "flow", FLOW_TOL),
    ("boundaryResults.R1.outflow", "flow", FLOW_TOL),
    ("boundaryResults.R1.portOutflows.p", "flow", FLOW_TOL),
    ("pumpResults.P1.curve.1.flow", "flow", FLOW_TOL),
    ("pumpResults.P1.systemCurve.1.flow", "flow", FLOW_TOL),
    ("flags.0.details.flow", "flow", FLOW_TOL),
    ("trace.elements.C1.intermediates.0.value", "flow", FLOW_TOL),
    ("nodeResults.P1:discharge.egl", "head", 1.0e-6),
    ("nodeResults.P1:discharge.hgl", "head", 1.0e-6),
    ("linkResults.C1.headLoss", "head", 1.0e-6),
    ("linkResults.C1.segments.0.headLoss", "head", 1.0e-6),
    ("linkResults.C1.fittings.0.headLoss", "head", 1.0e-6),
    ("pumpResults.P1.operatingHead", "head", 1.0e-6),
    ("pumpResults.P1.curve.1.head", "head", 1.0e-6),
    ("branchResults.T1.pathHeadLosses.branch", "head", 1.0e-6),
    ("boundaryResults.R1.egl", "head", 1.0e-6),
    ("flags.0.details.headRise", "head", 1.0e-6),
    ("trace.elements.C1.intermediates.1.value", "head", 1.0e-6),
    ("nodeResults.P1:discharge.pressure", "pressure", PRESSURE_TOL),
    ("nodeResults.P1:discharge.absolutePressure", "pressure", PRESSURE_TOL),
    ("atmosphericPressure", "pressure", PRESSURE_TOL),
    ("trace.elements.C1.intermediates.2.value", "pressure", PRESSURE_TOL),
    ("trace.elements.C1.intermediates.3.value", "pressure", PRESSURE_TOL),
    ("pumpResults.P1.speed", "speed", 1.0e-9 * 0.8),
    ("flags.0.details.speed", "speed", 1.0e-9 * 0.8),
    ("trace.elements.C1.intermediates.4.value", "speed", 1.0e-9 * 0.8),
    ("pumpResults.P1.systemCurve.0.head", "curve_head", 1.0e-6),  # 10 m: 10⁻⁶ m is looser
    ("pumpResults.P1.systemCurve.1.head", "curve_head", 1.0e-8 * 1.49e8),  # 10⁻⁸ relative
    ("linkResults.C1.velocity", "other", 1.0e-6 * 12.166),
    ("linkResults.C1.frictionFactor", "other", 1.0e-6 * 0.0185),
    ("linkResults.C1.segments.0.velocity", "other", 1.0e-6 * 12.166),
    ("linkResults.C1.fittings.0.k", "other", 1.0e-6 * 0.3),
    ("nodeResults.P1:discharge.velocity", "other", 1.0e-6 * 12.166),
    ("nodeResults.P1:discharge.elevation", "other", 1.0e-6 * 1.0),
    ("pumpResults.P1.hydraulicPower", "other", 1.0e-6 * 29360.0),
    ("valveResults.V1.kEffective", "other", 1.0e-6 * 12.0),
    ("branchResults.T1.kFactors.branch", "other", 1.0e-6 * 1.2),
    ("flags.0.details.step", "other", 1.0e-6 * 0.25),
    ("fluid.density", "other", 1.0e-6 * RHO),
    ("trace.elements.C1.inputs.0.value", "other", 1.0e-6 * 0.1023),  # a diameter in m
    ("trace.elements.C1.intermediates.5.value", "other", 1.0e-6 * 1.2e6),
    ("trace.elements.C1.intermediates.6.value", "other", 1.0e-6 * 1.0e-3),  # Pa·s
]

# criterion 7: flows 10⁻¹¹ × the largest flow; heads 10⁻⁸ m or 10⁻¹¹ relative, whichever is
# looser, pressures as heads of ρg; speeds 10⁻¹¹ relative; every other number as the table
FIXED_CASES = [
    ("linkResults.C2.flow", "flow", 1.0e-11 * Q_MAX),
    ("pumpResults.P1.systemCurve.1.flow", "flow", 1.0e-11 * Q_MAX),
    ("nodeResults.P1:discharge.egl", "head", 1.0e-8),
    ("flags.0.details.headRise", "head", 1.0e-8),
    ("nodeResults.P1:discharge.pressure", "pressure", RHO * G * 1.0e-8),
    ("nodeResults.P1:discharge.absolutePressure", "pressure", RHO * G * 1.0e-8),
    ("pumpResults.P1.speed", "speed", 1.0e-11 * 0.8),
    ("pumpResults.P1.systemCurve.0.head", "curve_head", 1.0e-8),
    ("pumpResults.P1.systemCurve.1.head", "curve_head", 1.0e-11 * 1.49e8),
    ("linkResults.C1.velocity", "other", 1.0e-6 * 12.166),
]


@pytest.mark.parametrize(
    ("tolerances", "path", "quantity", "tol"),
    [(compare.DEFAULT_SETTINGS, *c) for c in DEFAULT_CASES]
    + [(compare.FIXED_POINT, *c) for c in FIXED_CASES],
)
@pytest.mark.parametrize("sign", [1.0, -1.0])
def test_a_number_just_inside_its_tolerance_is_accepted_and_just_outside_reported(
    tolerances: compare.Tolerances, path: str, quantity: str, tol: float, sign: float
) -> None:
    a = solved()
    value = at(a, path)
    (inside,) = judged(a, put(a, path, value + sign * INSIDE * tol), tolerances)
    assert (inside[0], inside[5]) == ("in", quantity)
    assert inside[4] == pytest.approx(INSIDE, rel=1e-4)
    (outside,) = judged(a, put(a, path, value + sign * OUTSIDE * tol), tolerances)
    assert (outside[0], outside[5]) == ("out", quantity)
    assert outside[4] == pytest.approx(OUTSIDE, rel=1e-4)


def test_pressure_at_a_large_value_takes_the_relative_term_at_the_fixed_point() -> None:
    """Criterion 7's pressures are heads of ρg: 10⁻¹¹ relative is looser above 10⁻⁸ ρg / 10⁻¹¹
    = 9.79·10⁶ Pa for this density."""
    big = 5.0e7
    a = put(solved(), "nodeResults.P1:discharge.pressure", big)
    tol = 1.0e-11 * big
    assert tol > RHO * G * 1.0e-8
    path = "nodeResults.P1:discharge.pressure"
    ((kind, *_),) = judged(a, put(a, path, big + INSIDE * tol), compare.FIXED_POINT)
    assert kind == "in"
    ((kind, *_),) = judged(a, put(a, path, big + OUTSIDE * tol), compare.FIXED_POINT)
    assert kind == "out"


def test_equal_values_and_nan_record_nothing() -> None:
    a = solved()
    assert judged(a, copy.deepcopy(a), compare.DEFAULT_SETTINGS) == []
    nan = put(a, "linkResults.C1.velocity", math.nan)
    assert judged(nan, copy.deepcopy(nan), compare.DEFAULT_SETTINGS) == []
    ((kind, _, _, _, ratio, _),) = judged(a, nan, compare.DEFAULT_SETTINGS)
    assert (kind, ratio) == ("out", math.inf)


def test_round_off_flows_exclude_every_other_number_and_count_them() -> None:
    """C3 carries 2·10⁻¹¹ m³/s = 2·10⁻¹⁰ × the largest flow: its velocity is round-off; its flow
    and head loss are still compared (as a flow and a head)."""
    a = solved()
    b = put(a, "linkResults.C3.velocity", 5.0e-9)
    ((kind, path, _, _, rel, zero),) = judged(a, b, compare.DEFAULT_SETTINGS)
    assert (kind, path, zero) == ("round-off", "/linkResults/C3/velocity", False)
    assert rel == pytest.approx(1.0 - 2.4 / 5.0)
    # reported as 0 on one side
    b0 = put(put(b, "linkResults.C3.flow", 0.0), "linkResults.C3.velocity", 0.0)
    kinds = {d[1]: (d[0], d[-1]) for d in judged(a, b0, compare.DEFAULT_SETTINGS)}
    assert kinds["/linkResults/C3/velocity"] == ("round-off", True)
    assert kinds["/linkResults/C3/flow"] == ("in", "flow")
    # just above 10⁻⁹ × the largest flow on both sides: compared, at 10⁻⁶ relative
    above = put(a, "linkResults.C3.flow", 1.0001e-9 * Q_MAX)
    ((kind, *_),) = judged(
        above, put(above, "linkResults.C3.velocity", 5.0e-9), compare.DEFAULT_SETTINGS
    )
    assert kind == "out"
    at_bound = put(a, "linkResults.C3.flow", 1.0e-9 * Q_MAX)
    ((kind, *_),) = judged(
        at_bound, put(at_bound, "linkResults.C3.velocity", 5.0e-9), compare.DEFAULT_SETTINGS
    )
    assert kind == "round-off"
    # heads of a round-off element are compared
    ((kind, *_, quantity),) = judged(
        a, put(a, "linkResults.C3.headLoss", 2.0e-6), compare.DEFAULT_SETTINGS
    )
    assert (kind, quantity) == ("out", "head")


def test_a_branch_is_round_off_where_one_of_its_ports_is() -> None:
    """A tee's K factors and port velocities follow its least port flow (a dead branch: 0)."""
    a = put(solved(), "branchResults.T1.portFlows.branch", 0.0)
    b = put(a, "branchResults.T1.kFactors.run_outlet", 1.0e-40)
    ((kind, path, *_, zero),) = judged(a, b, compare.DEFAULT_SETTINGS)
    assert (kind, path, zero) == ("round-off", "/branchResults/T1/kFactors/run_outlet", True)
    # a node result follows its own port: the tee's run_inlet port carries 0.06 m³/s
    a = put(a, "nodeResults", {"T1:run_inlet": {"velocity": 7.3}, "T1:branch": {"velocity": 0.0}})
    ((kind, *_),) = judged(
        a, put(a, "nodeResults.T1:run_inlet.velocity", 7.31), compare.DEFAULT_SETTINGS
    )
    assert kind == "out"
    ((kind, *_),) = judged(
        a, put(a, "nodeResults.T1:branch.velocity", 1e-9), compare.DEFAULT_SETTINGS
    )
    assert kind == "round-off"


def test_a_flag_detail_takes_its_flags_element() -> None:
    a = put(solved(), "pumpResults.P1.operatingFlow", 0.0)
    ((kind, *_),) = judged(a, put(a, "flags.0.details.step", 0.5), compare.DEFAULT_SETTINGS)
    assert kind == "round-off"
    a = put(a, "flags.0.connectionId", "C2")  # a connection's flag: C2 carries 0.05 m³/s
    ((kind, *_),) = judged(a, put(a, "flags.0.details.step", 0.5), compare.DEFAULT_SETTINGS)
    assert kind == "out"


def test_an_equipment_result_is_an_element_with_its_quantities() -> None:
    """An equipment item's result (proposal equipment-pressure-drop.md §2.2) takes the tolerance
    of its quantity, its pressure loss that of a pressure (ρg × its head loss); its flow counts
    in the largest flow, and its other numbers are round-off where it carries a round-off
    flow."""
    item = {"flow": 0.05, "flowRatio": 1.25, "headLoss": 3.0, "pressureLoss": 2.9e4}
    a = put(solved(), "equipmentResults", {"E1": {**item, "pressureDrop": 2.8e4}})
    for field, quantity, tol in (
        ("flow", "flow", FLOW_TOL),
        ("headLoss", "head", 1.0e-6),
        ("pressureLoss", "pressure", PRESSURE_TOL),
        ("pressureDrop", "pressure", PRESSURE_TOL),
        ("flowRatio", "other", 1.0e-6 * 1.25),
    ):
        path = f"equipmentResults.E1.{field}"
        for multiple, kind in ((INSIDE, "in"), (OUTSIDE, "out")):
            ((got, *_, ratio, judged_as),) = judged(
                a, put(a, path, at(a, path) + multiple * tol), compare.DEFAULT_SETTINGS
            )
            assert (got, judged_as) == (kind, quantity), field
            assert ratio == pytest.approx(multiple, rel=1e-4), field
    # the largest flow: E1 carrying 0.2 m³/s sets a flow's tolerance
    big = put(a, "equipmentResults.E1.flow", 0.2)
    ((got, *_),) = judged(
        big, put(big, "linkResults.C2.flow", 0.05 + 0.99e-8 * 0.2), compare.DEFAULT_SETTINGS
    )
    assert got == "in"
    # a round-off flow through E1, and a flag on E1: its other numbers are excluded
    tiny = put(a, "equipmentResults.E1.flow", 1.0e-12)
    ((got, path, *_),) = judged(
        tiny, put(tiny, "equipmentResults.E1.flowRatio", 2.0e-10), compare.DEFAULT_SETTINGS
    )
    assert (got, path) == ("round-off", "/equipmentResults/E1/flowRatio")
    flagged = put(tiny, "flags.0.componentId", "E1")
    ((got, *_),) = judged(
        flagged, put(flagged, "flags.0.details.step", 0.5), compare.DEFAULT_SETTINGS
    )
    assert got == "round-off"


def test_an_orifice_result_is_an_element_with_its_quantities() -> None:
    """An orifice plate's result (proposal orifice-plate.md §2.2, §7.4) takes the tolerance of
    its quantity: its pressure loss, differential pressure (the reading at its taps) and
    vena-contracta pressure those of a pressure, ρg·10⁻⁶ m, not 10⁻⁶ relative; its flow counts in
    the largest flow, and its other numbers (β, Re, C, K) are round-off where it carries a
    round-off flow."""
    item = {
        "flow": 0.05,
        "headLoss": 3.0,
        "pressureLoss": 2.9e4,
        "pressureDrop": 2.8e4,
        "differentialPressure": 4.1e4,
        "venaContractaPressure": -1.5e4,
        "beta": 0.5,
        "reynoldsNumber": 6.0e5,
        "dischargeCoefficient": 0.6047,
        "lossCoefficient": 30.05,
    }
    a = put(solved(), "orificeResults", {"OR1": item})
    for field, quantity, tol in (
        ("flow", "flow", FLOW_TOL),
        ("headLoss", "head", 1.0e-6),
        ("pressureLoss", "pressure", PRESSURE_TOL),
        ("pressureDrop", "pressure", PRESSURE_TOL),
        ("differentialPressure", "pressure", PRESSURE_TOL),
        ("venaContractaPressure", "pressure", PRESSURE_TOL),
        ("dischargeCoefficient", "other", 1.0e-6 * 0.6047),
        ("lossCoefficient", "other", 1.0e-6 * 30.05),
    ):
        path = f"orificeResults.OR1.{field}"
        for multiple, kind in ((INSIDE, "in"), (OUTSIDE, "out")):
            ((got, *_, ratio, judged_as),) = judged(
                a, put(a, path, at(a, path) + multiple * tol), compare.DEFAULT_SETTINGS
            )
            assert (got, judged_as) == (kind, quantity), field
            assert ratio == pytest.approx(multiple, rel=1e-4), field
    # the largest flow: OR1 carrying 0.2 m³/s sets a flow's tolerance
    big = put(a, "orificeResults.OR1.flow", 0.2)
    ((got, *_),) = judged(
        big, put(big, "linkResults.C2.flow", 0.05 + 0.99e-8 * 0.2), compare.DEFAULT_SETTINGS
    )
    assert got == "in"
    # a round-off flow through OR1, and a flag on OR1: its other numbers are excluded
    tiny = put(a, "orificeResults.OR1.flow", 1.0e-12)
    ((got, path, *_),) = judged(
        tiny, put(tiny, "orificeResults.OR1.reynoldsNumber", 7.0e5), compare.DEFAULT_SETTINGS
    )
    assert (got, path) == ("round-off", "/orificeResults/OR1/reynoldsNumber")
    flagged = put(tiny, "flags.0.componentId", "OR1")
    ((got, *_),) = judged(
        flagged, put(flagged, "flags.0.details.step", 0.5), compare.DEFAULT_SETTINGS
    )
    assert got == "round-off"


def test_a_flag_detail_index_compares_exactly_on_a_round_off_element(tmp_path: Path) -> None:
    """``Flag.details`` holds floats, so the index of the pipe or fitting a flag names is a float
    in the dumps (``segmentIndex`` 0.0); it compares exactly, as an integer does, also where its
    element carries a round-off flow, whose other numbers are excluded: a flag that moves to
    another pipe of such a connection makes the project different (review finding V3)."""
    a = put(solved(), "flags.0.connectionId", "C3")  # C3 carries 2·10⁻¹¹ m³/s: round-off
    for key in ("segmentIndex", "fittingIndex"):
        a_i = put(a, f"flags.0.details.{key}", 0.0)
        b_i = put(a_i, f"flags.0.details.{key}", 1.0)
        ((kind, path, va, vb, *_),) = judged(a_i, b_i, compare.DEFAULT_SETTINGS)
        assert (kind, path, va, vb) == ("val", f"/flags[0]/details/{key}", 0.0, 1.0)
        ((kind, *_),) = judged(a_i, b_i, compare.FIXED_POINT)
        assert kind == "val"
    ((kind, *_),) = judged(a, put(a, "flags.0.details.step", 0.5), compare.DEFAULT_SETTINGS)
    assert kind == "round-off"  # the flag's other numbers stay round-off
    # The flag of the review's probe: TRANSITIONAL_FLOW on C3, pipe 1 on one side, pipe 2 on
    # the other (the message's number is masked; the index is not)
    flag = {
        "code": "TRANSITIONAL_FLOW",
        "componentId": None,
        "connectionId": "C3",
        "portId": None,
        "message": "connection 'C3' pipe 1: transitional flow (Re = 2500)",
        "details": {"reynoldsNumber": 2500.0, "segmentIndex": 0.0},
    }
    moved = copy.deepcopy(flag)
    moved["message"] = "connection 'C3' pipe 2: transitional flow (Re = 2500)"
    moved["details"]["segmentIndex"] = 1.0
    for side, doc in (("a", put(a, "flags", [flag])), ("b", put(a, "flags", [moved]))):
        (tmp_path / side).mkdir()
        (tmp_path / side / "p.json").write_text(json.dumps(doc))
    lines, different = compare.compare_dirs(
        tmp_path / "a", tmp_path / "b", tolerances=compare.DEFAULT_SETTINGS
    )
    assert different
    assert lines[0] == "identical 0, within tolerance 0, different 1"


def test_mask() -> None:
    text = "PRV 'PRV1' is closed (setpoint 199318, −0.5 m, Re = 4.311e+03, 1e-06 <= ε/D)"
    assert compare.mask(text) == "PRV 'PRV1' is closed (setpoint #, # m, Re = #, # <= ε/D)"
    assert compare.mask("ids PU4, port_1, H1, PU-1 and fluids 1.3.1 (2nd)") == (
        "ids PU4, port_1, H1, PU-1 and fluids # (2nd)"
    )
    assert compare.mask("(-142508 Pa) at 10⁻⁶ m³/s; Re^0.9") == "(# Pa) at #⁻⁶ m³/s; Re^#"
    for atom in ("1.1.0", "PU4:discharge", "0.5", "laminar"):
        assert compare.mask(atom) == atom  # no whitespace: an id, state or version


def test_strings_compare_masked_and_atoms_exactly() -> None:
    a = solved()
    note = "trace.elements.C1.notes.0"
    assert (
        judged(
            a,
            put(a, note, "Pipe 1: turbulent, Re = 1.3e+06 ≥ 4000: Colebrook."),
            compare.DEFAULT_SETTINGS,
        )
        == []
    )
    ((kind, path, ea, eb, flows),) = judged(
        a,
        put(a, note, "Pipe 1: laminar, Re = 1.2e+06 ≥ 4000: Colebrook."),
        compare.DEFAULT_SETTINGS,
    )
    assert (kind, path) == ("val", "/trace/elements/C1/notes[0]")
    assert (ea, eb) == (
        "Pipe #: turbulent, Re = # ≥ #: Colebrook.",
        "Pipe #: laminar, Re = # ≥ #: Colebrook.",
    )
    assert flows == "element |Q| 0.1 / 0.1"
    message = "flags.0.message"
    ((kind, *_),) = judged(
        a,
        put(a, message, "pump 'P2' runs at 0.1 m³/s, beyond its curve's 0.08 m³/s"),
        compare.DEFAULT_SETTINGS,
    )
    assert kind == "val"  # an id in a text keeps its digits
    ((kind, path, va, vb, flows),) = judged(
        a, put(a, "valveResults.V1.state", "open"), compare.DEFAULT_SETTINGS
    )
    assert (kind, path, va, vb, flows) == (
        "val",
        "/valveResults/V1/state",
        "active",
        "open",
        "element |Q| 0.05 / 0.05",
    )
    assert judged(a, put(a, "methodVersion", "1.2.0"), compare.DEFAULT_SETTINGS)[0][:4] == (
        "val",
        "/methodVersion",
        "1.1.0",
        "1.2.0",
    )


def test_booleans_integers_nulls_and_lengths_compare_exactly() -> None:
    a = solved()
    d = compare.DEFAULT_SETTINGS
    assert judged(a, put(a, "converged", False), d) == [("val", "/converged", True, False)]
    assert judged(a, put(a, "linkResults.C1.fittings.0.quantity", 3), d)[0][:4] == (
        "val",
        "/linkResults/C1/fittings[0]/quantity",
        2,
        3,
    )
    ((kind, *_),) = judged(a, put(a, "pumpResults.P1.speed", None), d)
    assert kind == "val"
    curve = at(a, "pumpResults.P1.systemCurve")
    longer = put(a, "pumpResults.P1.systemCurve", [*curve, {"flow": 0.2, "head": 5.0}])
    assert judged(a, longer, d) == [("len", "/pumpResults/P1/systemCurve", 2, 3)]


def write(directory: Path, name: str, data: object) -> None:
    directory.mkdir(exist_ok=True)
    (directory / f"{name}.json").write_text(json.dumps(data, sort_keys=True))


def example(root: Path) -> tuple[Path, Path]:
    """The exact-mode example: identical, numeric and other differences, an ignore, projects
    missing on either side, an unreadable file and a file starting with '_'."""
    a, b = root / "a", root / "b"
    base: dict[str, Any] = {
        "converged": True,
        "methodVersion": "1.1.0",
        "timestamp": "2026-10-24T00:00:00Z",
        "linkResults": {"C1": {"flow": 0.1, "headLoss": 2.5, "flowRegime": "turbulent"}},
        "pumpResults": {"P1": {"speed": 0.9, "systemCurve": [{"flow": 0.0, "head": 30.0}]}},
        "flags": [{"code": "ISOLATED_SECTION", "message": "part 'T1' carries 0.002 m³/s"}],
    }
    write(a, "p1", base)
    write(b, "p1", {**base, "timestamp": "2026-10-25T00:00:00Z"})
    changed = copy.deepcopy(base)
    changed["methodVersion"] = "1.2.0"
    changed["linkResults"]["C1"]["flow"] = 0.1 + 1e-12
    changed["linkResults"]["C1"]["headLoss"] = 2.6
    changed["flags"][0]["message"] = "part 'T1' carries 0.003 m³/s"
    changed["pumpResults"]["P1"]["systemCurve"].append({"flow": 0.1, "head": 20.0})
    changed["pumpResults"]["P1"]["control"] = None
    write(a, "p2", base)
    write(b, "p2", changed)
    write(a, "p3", base)
    write(b, "p3", {**base, "converged": False, "methodVersion": "1.2.0"})
    write(a, "p4", base)
    write(b, "p5", base)
    write(a, "p6", base)
    (b / "p6.json").write_text('{"converged": tr')
    write(a, "_times", {"p1": 1.0})
    return a, b


# the output of compare.py at d78a8ef (before --within-tolerance) on ``example``
EXACT = [
    "missing in B: p4.json",
    "unreadable: p6.json: B JSONDecodeError: Expecting value: line 1 column 15 (char 14)",
    "missing in A: p5.json",
    "identical 1, different 3",
    "  p2.json: 2 numeric diffs, max rel 0.0385; other: [('val', '/flags[0]/message', \"part"
    " 'T1' carries 0.002 m³/s\", \"part 'T1' carries 0.003 m³/s\"), ('val', '/methodVersion',"
    " '1.1.0', '1.2.0'), ('key', '/pumpResults/P1/control', '<missing>', 'None')]",
    "  p3.json: 0 numeric diffs, max rel 0; other: [('val', '/converged', 'True', 'False'),"
    " ('val', '/methodVersion', '1.1.0', '1.2.0')]",
]
EXACT_IGNORING = [
    *EXACT[:4],
    "ignored methodVersion: 3 values in 3 projects",
    "ignored pumpResults.*.control (null or absent): 1 values in 1 projects",
    "  p2.json: 2 numeric diffs, max rel 0.0385; other: [('val', '/flags[0]/message', \"part"
    " 'T1' carries 0.002 m³/s\", \"part 'T1' carries 0.003 m³/s\"), ('len',"
    " '/pumpResults/P1/systemCurve', '1', '2')]",
    "  p3.json: 0 numeric diffs, max rel 0; other: [('val', '/converged', 'True', 'False')]",
]


def test_exact_mode_output_is_unchanged(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    a, b = example(tmp_path)
    assert compare.compare_dirs(a, b) == (EXACT, 3)
    ignores = ["methodVersion"], ["pumpResults.*.control"]
    assert compare.compare_dirs(a, b, *ignores) == (EXACT_IGNORING, 3)
    with pytest.raises(SystemExit) as stop:
        compare.main(
            [str(a), str(b), "--ignore", "methodVersion", "--ignore-null", "pumpResults.*.control"]
        )
    assert stop.value.code == 1
    assert capsys.readouterr().out == "\n".join(EXACT_IGNORING) + "\n"


def test_within_tolerance_report(tmp_path: Path) -> None:
    a_dir, b_dir = tmp_path / "a", tmp_path / "b"
    base = solved()
    write(a_dir, "same", base)
    write(b_dir, "same", base)
    write(a_dir, "close", base)
    close = put(base, "nodeResults.P1:discharge.egl", 52.0 + 0.5e-6)
    close = put(close, "linkResults.C3.velocity", 9.9e-9)  # round-off
    close = put(
        close, "trace.elements.C1.notes.0", "Pipe 1: turbulent, Re = 1.3e+06 ≥ 4000: Colebrook."
    )
    write(b_dir, "close", put(close, "convergence.innerIterations", 9))
    write(a_dir, "far", base)
    far = put(base, "pumpResults.P1.speed", 0.8 * (1 + 2e-9))
    far = put(far, "valveResults.V1.state", "open")
    write(b_dir, "far", far)
    write(a_dir, "stuck", put(base, "converged", False))
    write(b_dir, "stuck", put(base, "converged", False))
    lines, diff = compare.compare_dirs(
        a_dir, b_dir, ["convergence.*"], tolerances=compare.DEFAULT_SETTINGS
    )
    assert diff == 1
    assert lines[0] == "identical 2, within tolerance 1, different 1"
    assert lines[1] == "ignored convergence.*: 8 values in 4 projects"
    assert lines[2].startswith(
        "tolerances: flow 1e-08 × the project's largest |flow| + 1e-14 m³/s;"
    )
    assert lines[3] == "largest |Δ|/tolerance of the 2 numbers that differ, in 2 projects:"
    assert lines[4:10] == [
        "  flow: no difference",
        "  head 0.5: close.json /nodeResults/P1:discharge/egl",
        "  pressure: no difference",
        f"  speed {2.0:.3g}: far.json /pumpResults/P1/speed",
        "  curve_head: no difference",
        "  other: no difference",
    ]
    assert lines[10] == (
        "excluded as round-off: 1 numbers in 1 projects (0 of an element whose flow is reported"
        " as 0 on a side, 1 of one carrying at most 1e-09 × the largest flow); largest relative"
        " difference 0.758: close.json /linkResults/C3/velocity"
    )
    assert lines[11] == "not converged or not solved on a side: 1"
    assert lines[12] == (
        "  stuck.json: A not converged (energy residual None): converged: 7 Newton iterations;"
        " B not converged (energy residual None): converged: 7 Newton iterations"
    )
    assert lines[13] == "different: 1"
    assert lines[14].startswith(
        "  far.json: 1 numbers out of tolerance, worst |Δ|/tolerance 2 (speed"
    )
    assert lines[14].endswith(
        "1 other differences: [('val', '/valveResults/V1/state', 'active', 'open',"
        " 'element |Q| 0.05 / 0.05')]"
    )
    assert len(lines) == 15


def test_group_counts_apart(tmp_path: Path) -> None:
    a_dir, b_dir = tmp_path / "a", tmp_path / "b"
    base = solved()
    no_prv = copy.deepcopy(base)
    del no_prv["trace"]["elements"]["PRV1"]
    failed = put(base, "trace.elements.PRV1.inputs.1.value", "failed_open")
    for name, doc, changed in (
        ("prv_same", base, base),
        ("prv_moved", base, put(base, "linkResults.C2.flow", 0.05 + 1e-10)),
        ("plain_same", no_prv, no_prv),
        ("failed_moved", failed, put(failed, "linkResults.C2.flow", 0.05 + 1e-10)),
    ):
        write(a_dir, name, doc)
        write(b_dir, name, changed)
    group = compare.parse_group("Valve type=prv, Status=active")
    assert group == {"Valve type": "prv", "Status": "active"}
    lines, diff = compare.compare_dirs(a_dir, b_dir, group=group)
    assert diff == 2
    assert lines[1:3] == [
        "group 'Valve type=prv,Status=active': identical 1, different 1",
        "others: identical 1, different 1",
    ]
    lines, diff = compare.compare_dirs(
        a_dir, b_dir, tolerances=compare.DEFAULT_SETTINGS, group=group
    )
    assert diff == 0
    assert lines[1:3] == [
        "group 'Valve type=prv,Status=active': identical 1, within tolerance 1, different 0",
        "others: identical 1, within tolerance 1, different 0",
    ]
    with pytest.raises(ValueError, match="NAME=VALUE"):
        compare.parse_group("Valve type")


def test_command_line_options(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    a_dir, b_dir = tmp_path / "a", tmp_path / "b"
    base = solved()
    write(a_dir, "p", base)
    write(b_dir, "p", put(base, "linkResults.C2.flow", 0.05 + 0.5e-12))
    with pytest.raises(SystemExit) as stop:
        compare.main([str(a_dir), str(b_dir), "--within-tolerance", "--fixed-point"])
    assert stop.value.code == 0
    out = capsys.readouterr().out
    assert out.startswith("identical 0, within tolerance 1, different 0\n")
    assert "tolerances: flow 1e-11 × the project's largest |flow| + 0 m³/s" in out
    write(b_dir, "p", put(base, "linkResults.C2.flow", 0.05 + 2e-12))
    with pytest.raises(SystemExit) as stop:
        compare.main([str(a_dir), str(b_dir), "--within-tolerance", "--fixed-point"])
    assert stop.value.code == 1
    with pytest.raises(SystemExit) as stop:
        compare.main([str(a_dir), str(b_dir), "--within-tolerance"])
    assert stop.value.code == 0
    capsys.readouterr()
    with pytest.raises(SystemExit) as stop:
        compare.main([str(a_dir), str(b_dir), "--fixed-point"])
    assert stop.value.code == 2  # needs --within-tolerance
    assert "--fixed-point needs --within-tolerance" in capsys.readouterr().err


# --------------------------------------------------------------------------- corpus.py


def test_solver_options_are_parsed_and_checked() -> None:
    assert corpus.solver_options("tolerance=1e-13,max_iterations=1000") == {
        "tolerance": 1.0e-13,
        "max_iterations": 1000,
    }
    assert corpus.solver_options(" friction_method = swamee_jain ") == {
        "friction_method": "swamee_jain"
    }
    for text, reason in (
        ("tolerance", "NAME=VALUE"),
        ("tol=1e-13", "unknown solver option 'tol'"),
        ("tolerance=1e-13,tolerance=1e-12", "given twice"),
        ("tolerance=0", "tolerance: Input should be greater than 0"),
        ("max_iterations=1001", "max_iterations: Input should be less than or equal to 1000"),
        ("max_iterations=1e3", "max_iterations: Input should be a valid integer"),
        ("friction_method=hazen", "friction_method: Input should be 'colebrook' or 'swamee_jain'"),
    ):
        with pytest.raises(ValueError, match=reason):
            corpus.solver_options(text)


def reference_project() -> Project:
    path = API_ROOT / "tests" / "reference" / "cases" / "prv_active.json"
    return corpus.load(("file", str(path), 11))


def test_with_solver_options_replaces_only_those_fields() -> None:
    project = reference_project()
    own = project.settings.solver_options
    tight = corpus.with_solver_options(project, {"tolerance": 1.0e-13, "max_iterations": 1000})
    assert tight.settings.solver_options.tolerance == 1.0e-13
    assert tight.settings.solver_options.max_iterations == 1000
    assert tight.settings.solver_options.friction_method == own.friction_method
    assert project.settings.solver_options == own  # the loaded project is unchanged
    unchanged = tight.model_copy(update={"settings": project.settings})
    assert unchanged == project
    assert corpus.with_solver_options(project, {}) is project


def test_run_solves_with_the_override(tmp_path: Path) -> None:
    path = API_ROOT / "tests" / "reference" / "cases" / "prv_active.json"
    item = ("ref_prv_active", ("file", str(path), 11))
    options = corpus.solver_options("tolerance=1e-13,max_iterations=1000")
    assert corpus.run(item, str(tmp_path), options)[:2] == ("ref_prv_active", "ok")
    items = json.loads((tmp_path / "ref_prv_active.json").read_text())["trace"]["methods"]
    texts = [t for s in items["sections"] for t in s["items"]]
    assert any("flow tolerance 1e-13" in t and "at most 1000 Newton iterations" in t for t in texts)
    default = tmp_path / "default"
    default.mkdir()
    assert corpus.run(item, str(default))[1] == "ok"
    items = json.loads((default / "ref_prv_active.json").read_text())["trace"]["methods"]
    texts = [t for s in items["sections"] for t in s["items"]]
    assert not any("flow tolerance 1e-13" in t for t in texts)


def test_resume_refuses_other_solver_options(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "dump"
    out.mkdir()
    (out / "ref_x.json").write_text("{}")  # a dump made without an override
    corpus.main([str(out), "--resume", "--dry-run", "--only", "ref_prv_active"])
    with pytest.raises(SystemExit, match="was dumped with solver options"):
        corpus.main([str(out), "--resume", "--dry-run", "--solver-options", "tolerance=1e-13"])
    (out / "_solver_options.json").write_text(json.dumps({"tolerance": 1e-13}))
    corpus.main([str(out), "--resume", "--dry-run", "--solver-options", "tolerance=1e-13"])
    assert "solver options of every project: tolerance=1e-13" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="was dumped with solver options"):
        corpus.main([str(out), "--resume", "--dry-run"])
    with pytest.raises(SystemExit) as stop:
        corpus.main([str(out), "--resume", "--dry-run", "--solver-options", "tolerance=-1"])
    assert stop.value.code == 2
    assert "--solver-options: tolerance: Input should be greater than 0" in capsys.readouterr().err
