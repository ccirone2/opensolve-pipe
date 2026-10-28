"""Unit checks of the differential test's own pieces (TSD §10.4) for flow-controlled pumps,
assigned-flow nodes and the corpus comparison: the rule checker written from proposal
vfd-pump-modes.md §4.5 at its tolerance edges, the closed-form implied speed, the 'flow_control'
generator profile, the EPANET substitutes, the control search's split of distinct valid states
into multiple states and alternatives at rest, the networks without a steady state that
assigned flows make (``checks.assigned_flow_expectations``), the 'assigned_flow' generator
profile and its EPANET demands, ``compare --ignore``, ``--ignore-null`` and ``--ignore-empty``
(with the orifice plate's proof command, proposal orifice-plate.md §3.9), and the check of
pumps and valves without a result (``checks.missing_result_problems``: a result deleted from a
solve where flow runs, in a floating section or from a dead-headed pump is reported, and the
results the rule leaves out are not). Fast; no EPANET run (the WNTR model build is skipped where
WNTR is not installed).
"""

import copy
import json
from pathlib import Path
from typing import Any, Literal

import pytest

pytest.importorskip("wntr")  # checks reads EPANET results (a dev dependency, so CI runs this)

from opensolve_pipe.models.components import AssignedFlow, Component, Plug, Pump, PumpControl
from opensolve_pipe.models.piping import PipeConnection
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import SolvedState
from opensolve_pipe.services.solver import solve_project
from opensolve_pipe.services.solver.builder import validate_topology
from tests.differential import checks as ck
from tests.differential import compare
from tests.differential import epanet_model as em
from tests.differential import state_search as ss
from tests.differential.fuzz import plug_twin
from tests.differential.generator import ASSIGNED_FLOW, DEFAULT, FLOW_CONTROL, generate
from tests.differential.missing_result_check import without
from tests.reference import element_laws as el
from tests.reference import network_check as nc
from tests.reference.case_format import (
    assigned_flow,
    check_valve,
    connect,
    control_valve,
    custom_fluid,
    custom_pipe,
    ideal_tee,
    isolation_valve,
    make_project,
    plug,
    pump,
    pump_curve,
    reservoir,
)

A, B = 40.0, 2000.0  # test curve H₀ = A − B·x (m, m per m³/s): random test inputs
CURVE = pump_curve("PC", [(0.0, A), (0.005, A - B * 0.005), (0.01, A - B * 0.01)])
Q_SET, S_MIN, S_MAX = 0.004, 0.5, 0.9
PUMP = pump("PU", 0.0, "PC", speed=S_MAX).model_copy(
    update={"control": PumpControl(mode="flow", setpoint=Q_SET, min_speed=S_MIN)}
)
HTOL, QTOL = ck.HTOL, ck.QTOL


def head(speed: float, q: float) -> float:
    return el.pump_head(CURVE, speed, q)


F_MIN, F_MAX = head(S_MIN, Q_SET), head(S_MAX, Q_SET)
S_MIN_SHUT, S_MAX_SHUT = head(S_MIN, 0.0), head(S_MAX, 0.0)


@pytest.mark.parametrize(
    ("state", "gain", "q", "expected"),
    [
        # active: A1, A2; a boundary point keeps the state (proposal §4.6)
        ("active", F_MAX + HTOL, Q_SET, "active"),
        ("active", F_MAX + 2 * HTOL, Q_SET, "max_speed"),
        ("active", F_MIN - HTOL, Q_SET, "active"),
        ("active", F_MIN - 2 * HTOL, Q_SET, "min_speed"),
        # max_speed: X1 (Q ≥ Q_set), X2 (v1 pumpstatus at S_max)
        ("max_speed", F_MAX, Q_SET, "active"),
        ("max_speed", F_MAX, 0.9 * Q_SET, "max_speed"),
        ("max_speed", S_MAX_SHUT + HTOL, 0.0, "max_speed"),
        ("max_speed", S_MAX_SHUT + 2 * HTOL, 0.0, "no_flow"),
        ("max_speed", F_MAX, -2 * QTOL, "no_flow"),
        # min_speed: N1 (Q ≤ Q_set), N2 (v1 pumpstatus at S_min)
        ("min_speed", F_MIN, Q_SET, "active"),
        ("min_speed", F_MIN, 1.1 * Q_SET, "min_speed"),
        ("min_speed", S_MIN_SHUT + 2 * HTOL, 1.1 * Q_SET, "no_flow"),
        # no_flow: C1 (re-opens at maximum speed once H ≤ S_max)
        ("no_flow", S_MAX_SHUT, 0.0, "max_speed"),
        ("no_flow", S_MAX_SHUT + HTOL / 2, 0.0, "no_flow"),
    ],
)
def test_rule_flow_pump(state: str, gain: float, q: float, expected: str) -> None:
    assert ck.rule_flow_pump(state, gain, q, PUMP, CURVE) == expected


def _pump_with(q_set: float, s_min: float, s_max: float = S_MAX) -> Pump:
    return pump("PU", 0.0, "PC", speed=s_max).model_copy(
        update={"control": PumpControl(mode="flow", setpoint=q_set, min_speed=s_min)}
    )


def test_rule_a2_tests_the_lowest_head_of_the_stable_bracket() -> None:
    """A2 bounds by F(s_lo, Q_set), s_lo = max(s_min, Q_set/x_mono) (proposal §4.3, §4.5). On
    the test curve x_mono = 2A/B = 0.04 m³/s; Q_set = 0.004 with s_min = 0.05 gives s_lo = 0.1,
    F(s_lo, Q_set) = 0.01 (40 − 80) = −0.4 m below F(s_min, Q_set) = 0.0025 (40 − 160) = −0.3 m.
    A head between them is held by a speed on [s_lo, s_max]: active, not min_speed."""
    low = _pump_with(0.004, 0.05)
    f_lo, f_min = head(0.1, 0.004), head(0.05, 0.004)
    assert f_lo == pytest.approx(-0.4, rel=1e-12)
    assert f_min == pytest.approx(-0.3, rel=1e-12)
    assert ck.rule_flow_pump("active", -0.35, 0.004, low, CURVE) == "active"
    assert ck.rule_flow_pump("active", f_lo - HTOL, 0.004, low, CURVE) == "active"
    assert ck.rule_flow_pump("active", f_lo - 2 * HTOL, 0.004, low, CURVE) == "min_speed"
    band = ck.active_band(low, CURVE, "s", "d")
    assert band == [("s", "d", head(S_MAX, 0.004) + HTOL, "PU"), ("d", "s", -(f_lo - HTOL), "PU")]


def test_rule_a2_with_the_bracket_capped_at_the_maximum_speed() -> None:
    """s_lo is at most s_max: Q_set = 0.04 at s_max = 0.9 puts Q_set/s_max = 0.0444 beyond
    x_mono = 0.04, so F(·, Q_set) falls on the whole range and only F(s_max, Q_set) ± Htol is
    active. The uncapped Q_set/x_mono = 1.0 would give F(1, Q_set) = 40 − 80 = −40 m, below
    F(s_max, Q_set) = 0.81 (40 − 2000 · 0.04/0.9) = −39.6 m, and accept a head between them.
    The API rejects such a setpoint (Q_set >= s_max x_mono, CONTROLLED_PUMP_SETPOINT) since the
    owner's decision of 2026-10-23, so no fuzz network has one; this checks the checker's rule
    on its own."""
    capped = _pump_with(0.04, 0.5)
    f_max = head(S_MAX, 0.04)
    assert head(1.0, 0.04) == pytest.approx(-40.0, rel=1e-12)
    assert f_max == pytest.approx(-39.6, rel=1e-12)
    assert ck.rule_flow_pump("active", f_max, 0.04, capped, CURVE) == "active"
    assert ck.rule_flow_pump("active", -39.8, 0.04, capped, CURVE) == "min_speed"
    assert ck.rule_flow_pump("active", f_max + 2 * HTOL, 0.04, capped, CURVE) == "max_speed"


def test_rule_flow_pump_slack_widens_x1_and_n1() -> None:
    assert ck.rule_flow_pump("max_speed", F_MAX, Q_SET, PUMP, CURVE, q_slack=1e-9) == "max_speed"
    assert ck.rule_flow_pump("min_speed", F_MIN, Q_SET, PUMP, CURVE, q_slack=1e-9) == "min_speed"


def test_our_flow_at_the_setpoint_but_for_rounding_is_the_setpoint() -> None:
    """A limit state whose flow is Q_set but for rounding is not a fixed point (ours)."""
    slack = -ck.FLOW_ROUNDING * Q_SET
    below, above = Q_SET * (1 - 1e-12), Q_SET * (1 + 1e-12)
    assert ck.rule_flow_pump("max_speed", F_MAX, below, PUMP, CURVE, slack) == "active"
    assert ck.rule_flow_pump("min_speed", F_MIN, above, PUMP, CURVE, slack) == "active"
    assert ck.rule_flow_pump("max_speed", F_MAX, 0.99 * Q_SET, PUMP, CURVE, slack) == "max_speed"
    assert ck.rule_flow_pump("min_speed", F_MIN, 1.01 * Q_SET, PUMP, CURVE, slack) == "min_speed"


@pytest.mark.parametrize("gain", [F_MIN + 0.1, 0.5 * (F_MIN + F_MAX), F_MAX - 0.1])
def test_implied_speed_closed_form(gain: float) -> None:
    s = ck.implied_speed(CURVE, Q_SET, gain, S_MIN, S_MAX)
    assert S_MIN <= s <= S_MAX
    assert head(s, Q_SET) == pytest.approx(gain, abs=1e-9)


def test_implied_speed_clamps() -> None:
    assert ck.implied_speed(CURVE, Q_SET, F_MAX + 1.0, S_MIN, S_MAX) == S_MAX
    assert ck.implied_speed(CURVE, Q_SET, F_MIN - 1.0, S_MIN, S_MAX) == S_MIN


def test_implied_speed_needs_a_collinear_curve() -> None:
    bent = pump_curve("PB", [(0.0, 40.0), (0.005, 39.0), (0.01, 30.0)])
    with pytest.raises(ValueError, match="collinear"):
        ck.implied_speed(bent, Q_SET, 20.0, S_MIN, S_MAX)


def controlled(project: Project) -> list[Pump]:
    return [c for c in project.components if isinstance(c, Pump) and c.control is not None]


@pytest.mark.parametrize("seed", range(10_000, 10_040))
def test_flow_control_profile_adds_to_the_default_network(seed: int) -> None:
    base, fc = generate(seed), generate(seed, FLOW_CONTROL)
    assert generate(seed, DEFAULT) == base
    # every default component is there (a pump may have gained a control), the curves too
    fc_ids = {c.id: c for c in fc.components}
    for c in base.components:
        assert c.id in fc_ids
        assert c == fc_ids[c.id].model_copy(update={"control": None})
    assert fc.pump_library[: len(base.pump_library)] == base.pump_library
    pumps = controlled(fc)
    assert len(pumps) <= 2
    inserted = [p for p in pumps if p.id not in {c.id for c in base.components}]
    assert len(fc.connections) == len(base.connections) + len(inserted)
    curves = {cv.id: cv for cv in fc.pump_library}
    for p in pumps:
        assert p.control is not None
        assert 0.0 < p.control.min_speed < p.speed <= 1.0
        ck.collinear_curve(curves[p.curve_id])  # the closed-form speed applies
    # through the API JSON, as the corpus loads it
    assert Project.model_validate(fc.model_dump(mode="json", by_alias=True)) == fc


REJECTED_BEFORE = (10_443, 10_532, 11_131, 11_253, 12_108)
"""flow_control seeds whose equal-setpoint copy drew a setpoint at or beyond the new pump's
s_max x_mono (an independent scan with element_laws.x_mono), which the API rejects since the
owner's decision of 2026-10-23 (CONTROLLED_PUMP_SETPOINT). The generator now keeps that pump's
own drawn setpoint there, decided after the draws, so every other seed's network is unchanged
(all 3,000 seeds of both profiles compared as canonical JSON)."""


@pytest.mark.parametrize("seed", REJECTED_BEFORE)
def test_flow_control_profile_draws_no_rejected_setpoint(seed: int) -> None:
    project = generate(seed, FLOW_CONTROL)
    curves = {cv.id: cv for cv in project.pump_library}
    pumps = controlled(project)
    assert pumps
    for p in pumps:
        assert p.control is not None
        assert p.control.setpoint < p.speed * el.x_mono(curves[p.curve_id])
    assert validate_topology(project) == []


def test_control_pins_and_runs() -> None:
    project = generate(10_011, FLOW_CONTROL)
    on = [p.id for p in controlled(project) if p.status == "on"]
    assert on
    pins = em.control_pins(project, {})  # no state reported: at maximum speed (rule A0)
    assert pins == dict.fromkeys(on, "max_speed")
    states = dict.fromkeys(on, "active")
    assert em.control_runs(project, em.control_pins(project, states)) == states
    with pytest.raises(ValueError, match="needs its state"):
        em.control_runs(project, {})


def test_active_substitute_is_the_faq_demand_pair() -> None:
    project = generate(10_011, FLOW_CONTROL)
    on = [p for p in controlled(project) if p.status == "on"]
    p = on[0]
    assert p.control is not None
    others = {o.id: "max_speed" for o in on[1:]}
    wn, lay = em.build_wn(project, {}, {**others, p.id: "active"})
    q = p.control.setpoint
    demand = wn.get_node(f"{p.id}_suction").demand_timeseries_list[0].base_value
    assert demand == q
    assert wn.get_node(f"{p.id}_discharge").demand_timeseries_list[0].base_value == -q
    assert str(wn.get_link(p.id).initial_status).upper().endswith("CLOSED")
    assert lay.fixed_flow == {p.id: q}
    wn2, _ = em.build_wn(project, {}, {**others, p.id: "min_speed"})
    assert wn2.get_link(p.id).base_speed == p.control.min_speed
    assert str(wn2.get_link(p.id).initial_status).upper().endswith("OPEN")


@pytest.mark.parametrize(
    ("seed", "multiple"),
    [
        # a pump at its minimum speed carrying flow, or closed: the closed one's solution has
        # flow in a subset of the other's connections, with other flows there
        (11_285, True),
        # the closed pump's solution has the other's flows where it has flow
        (10_065, False),
    ],
)
def test_control_search_multiple_compares_shared_flows(seed: int, multiple: bool) -> None:
    project = generate(seed, FLOW_CONTROL)
    _, valid = ss.control_search(project)
    a, b = ss.distinct(project, valid)
    assert ss.flowing(b) < ss.flowing(a) or ss.flowing(a) < ss.flowing(b)
    assert ss.multiple(project, [a, b]) is multiple


# --------------------------------------------------------------------------- assigned flows
# Small networks of random test inputs: a reservoir R0 feeding an assigned-flow node AF1 through
# one element, whose inlet (suction) faces R0 unless reversed.

PIPE = [custom_pipe(0.1, 10.0, 1.0e-5)]
WATER = custom_fluid("EPANET water nu", 1000.0, em.NU_EPANET * 1000.0)


def line(element: Component | None, flow: float, *, reverse: bool = False) -> Project:
    comps: list[Component] = [reservoir("R0", 0.0, 5.0), assigned_flow("AF1", 0.0, flow)]
    if element is None:
        conns = [connect("C1", "R0:port_1", "AF1:port_1", PIPE)]
    else:
        comps.append(element)
        a, b = nc.two_port_ends(element)  # type: ignore[arg-type]
        a, b = (b, a) if reverse else (a, b)
        conns = [connect("C1", "R0:port_1", a, PIPE), connect("C2", b, "AF1:port_1", PIPE)]
    return make_project("t", "t", WATER, comps, conns, pump_library=[CURVE])


def kinds(project: Project) -> list[str]:
    return [e.kind for e in ck.assigned_flow_expectations(project)]


FCV = control_valve("FCV1", 0.0, "fcv", 0.01)


@pytest.mark.parametrize(
    ("element", "flow", "reverse", "expected"),
    [
        (None, 0.01, False, []),
        (isolation_valve("IV1", 0.0, "gate", status="isolated"), 0.01, False, ["disconnected"]),
        (isolation_valve("IV1", 0.0, "gate", status="isolated"), 0.0, False, []),
        (isolation_valve("IV1", 0.0, "gate"), -0.01, False, []),
        (check_valve("CV1", 0.0, "check"), 0.01, False, []),
        (check_valve("CV1", 0.0, "check"), -0.01, False, ["no_flow_path"]),
        (check_valve("CV1", 0.0, "check"), 0.01, True, ["no_flow_path"]),
        (check_valve("CV1", 0.0, "check", status="locked_open"), 0.01, True, []),
        (check_valve("CV1", 0.0, "check", status="locked_closed"), 0.01, False, ["disconnected"]),
        # an FCV passes at most its setpoint forwards: above it no pattern of flows, at it the
        # pressure behind it undetermined, below it the FCV open
        (FCV, 0.02, False, ["no_flow_path"]),
        (FCV, 0.01, False, ["over_controlled"]),
        (FCV, -0.01, True, ["over_controlled"]),
        (FCV, 0.01 * (1 + 0.5 * ck.FLOW_ROUNDING), False, ["over_controlled"]),
        (FCV, 0.005, False, []),
        (FCV, -0.005, False, ["no_flow_path"]),
        (FCV.model_copy(update={"status": "failed_open"}), 0.01, False, []),
        (FCV.model_copy(update={"status": "failed_closed"}), 0.01, False, ["disconnected"]),
        # a flow-controlled pump passes any forward flow (more than Q_set at its minimum speed)
        (PUMP, Q_SET, False, ["over_controlled"]),
        (PUMP, 2 * Q_SET, False, []),
        (PUMP, 0.5 * Q_SET, False, []),
        (PUMP, -Q_SET, False, ["no_flow_path"]),
        (PUMP.model_copy(update={"status": "off"}), Q_SET, False, ["disconnected"]),
        (pump("PF", 0.0, "PC"), -0.001, False, ["no_flow_path"]),
    ],
)
def test_assigned_flow_expectations_through_one_element(
    element: Component | None, flow: float, reverse: bool, expected: list[str]
) -> None:
    assert kinds(line(element, flow, reverse=reverse)) == expected


def parallel(flow: float, prv: str | None = None) -> Project:
    """R0 → FCV1 (0.01) → T1 ← FCV2 (0.02) ← R1 and T1 → AF1, or T1 → PRV1 → AF1."""
    comps: list[Component] = [
        reservoir("R0", 0.0, 5.0),
        reservoir("R1", 0.0, 5.0),
        control_valve("FCV1", 0.0, "fcv", 0.01),
        control_valve("FCV2", 0.0, "fcv", 0.02),
        ideal_tee("T1", 0.0),
        assigned_flow("AF1", 0.0, flow),
    ]
    conns = [
        connect("C1", "R0:port_1", "FCV1:inlet", PIPE),
        connect("C2", "FCV1:outlet", "T1:run_inlet", PIPE),
        connect("C3", "R1:port_1", "FCV2:inlet", PIPE),
        connect("C4", "FCV2:outlet", "T1:run_outlet", PIPE),
    ]
    if prv is None:
        conns.append(connect("C5", "T1:branch", "AF1:port_1", PIPE))
    else:
        comps.append(control_valve("PRV1", 0.0, "prv", 1.0e5, status=prv))  # type: ignore[arg-type]
        conns += [
            connect("C5", "T1:branch", "PRV1:inlet", PIPE),
            connect("C6", "PRV1:outlet", "AF1:port_1", PIPE),
        ]
    return make_project("t", "t", WATER, comps, conns)


def test_fcvs_in_parallel_at_their_setpoints_are_over_controlled() -> None:
    (e,) = ck.assigned_flow_expectations(parallel(0.03))
    assert (e.kind, e.every, e.any_of, e.word) == (
        "over_controlled",
        ("FCV1", "FCV2"),
        ("AF1",),
        "undetermined",
    )
    assert kinds(parallel(0.025)) == []  # one FCV open: its law ties the heads
    assert kinds(parallel(0.04)) == ["no_flow_path"]
    assert kinds(parallel(-0.01)) == ["no_flow_path"]


def test_an_active_prv_in_the_part_may_hold_its_head() -> None:
    """The part between the FCVs and AF1 holds an active PRV, whose outlet head is its setpoint:
    no over-control is claimed there; open for good, the PRV holds no head."""
    assert kinds(parallel(0.03, prv="active")) == []
    assert kinds(parallel(0.03, prv="failed_open")) == ["over_controlled"]
    assert kinds(parallel(0.04, prv="active")) == ["no_flow_path"]


def test_a_balanced_pair_closed_off_may_float() -> None:
    """Assigned flows that sum to zero in a closed-off part: a floating section (TSD §4.8)."""
    comps: list[Component] = [
        reservoir("R0", 0.0, 5.0),
        isolation_valve("IV1", 0.0, "gate", status="isolated"),
        ideal_tee("T1", 0.0),
        assigned_flow("AF1", 0.0, 0.01),
        assigned_flow("AF2", 0.0, -0.01),
    ]
    conns = [
        connect("C1", "R0:port_1", "IV1:inlet", PIPE),
        connect("C2", "IV1:outlet", "T1:run_inlet", PIPE),
        connect("C3", "T1:run_outlet", "AF1:port_1", PIPE),
        connect("C4", "T1:branch", "AF2:port_1", PIPE),
    ]
    project = make_project("t", "t", WATER, comps, conns)
    assert kinds(project) == []
    unbalanced = project.model_copy(
        update={"components": [*comps[:4], assigned_flow("AF2", 0.0, -0.005)]}
    )
    (e,) = ck.assigned_flow_expectations(unbalanced)
    assert (e.kind, e.any_of) == ("disconnected", ("AF1", "AF2"))


def test_expectation_named_by_quoted_ids() -> None:
    (e,) = ck.assigned_flow_expectations(line(FCV, 0.01))
    assert e.named("'FCV1' and 'AF1' fix the same flow: the pressure is undetermined")
    assert not e.named("'FCV1' and 'AF1' fix the same flow")
    assert not e.named("'FCV12' and 'AF12': the pressure is undetermined")
    (d,) = ck.assigned_flow_expectations(line(FCV, 0.02))
    assert d.named("no reservoir reaches assigned-flow node 'AF1'")
    assert not d.named("no reservoir reaches 'FCV1'")


def test_assigned_flow_is_an_epanet_junction_demand() -> None:
    project = line(None, -0.0123)
    wn, lay = em.build_wn(project, {}, {})
    junction = wn.get_node("AF1")
    assert junction.demand_timeseries_list[0].base_value == -0.0123
    assert junction.elevation == 0.0
    assert lay.node_of_port["AF1:port_1"] == "AF1"
    assert wn.options.hydraulic.demand_model == "DDA"


@pytest.mark.parametrize("seed", range(20_000, 20_040))
def test_assigned_flow_profile_adds_to_the_default_network(seed: int) -> None:
    base, af = generate(seed), generate(seed, ASSIGNED_FLOW)
    nodes = [c for c in af.components if isinstance(c, AssignedFlow)]
    assert len(nodes) <= 4
    af_ids = {c.id: c for c in af.components}
    removed = [c for c in base.components if c.id not in af_ids]
    assert all(isinstance(c, Plug) for c in removed)  # a node in a plug's place
    assert len(removed) <= len(nodes)
    for c in base.components:
        assert c.id not in af_ids or af_ids[c.id] == c
    assert af.pump_library[: len(base.pump_library)] == base.pump_library
    base_conns = {c.id for c in base.connections}
    assert base_conns <= {c.id for c in af.connections}
    for node in nodes:
        assert -100.0 <= node.flow <= 100.0
        assert node.flow == float(f"{node.flow:.6g}")
    assert validate_topology(af) == []
    assert Project.model_validate(af.model_dump(mode="json", by_alias=True)) == af


def test_plug_twin_replaces_only_zero_flows() -> None:
    project = line(None, 0.0)
    twin = plug_twin(project)
    assert twin is not None
    (p,) = [c for c in twin.components if c.id == "AF1"]
    assert isinstance(p, Plug)
    assert (p.elevation, p.ports) == (0.0, project.components[1].ports)
    assert plug_twin(line(None, 0.01)) is None


def write(directory: Path, name: str, data: object) -> None:
    directory.mkdir(exist_ok=True)
    (directory / f"{name}.json").write_text(json.dumps(data))


def test_compare_ignore(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    before = {"methodVersion": "1.0.0", "pumpResults": {"P1": {"speed": 1.0}}, "x": [1, 2]}
    after = {
        "methodVersion": "1.1.0",
        "pumpResults": {"P1": {"speed": 1.0, "control": None}},
        "x": [1, 2],
    }
    write(a, "p", before)
    write(b, "p", after)
    _, diff = compare.compare_dirs(a, b)
    assert diff == 1
    lines, diff = compare.compare_dirs(a, b, ["pumpResults.*.control", "methodVersion"])
    assert diff == 0
    assert "ignored pumpResults.*.control: 1 values in 1 projects" in lines
    # an ignore names whole paths at their depth: a change elsewhere still shows
    write(b, "p", {**after, "x": [1, 3]})
    _, diff = compare.compare_dirs(a, b, ["pumpResults.*.control", "methodVersion", "*.1"])
    assert diff == 0
    _, diff = compare.compare_dirs(a, b, ["pumpResults.*.control", "methodVersion", "x.0"])
    assert diff == 1
    _, diff = compare.compare_dirs(a, b, ["pumpResults.*.control", "version"])
    assert diff == 1


def test_compare_ignore_null(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    before = {"pumpResults": {"P1": {"speed": 1.0}, "P2": {"speed": 1.0, "control": None}}}
    control = {"mode": "flow", "setpoint": 0.01, "state": "max_speed", "setpointAchieved": False}
    write(a, "p", before)
    write(b, "p", {"pumpResults": {"P1": {"speed": 1.0, "control": None}, "P2": {"speed": 1.0}}})
    lines, diff = compare.compare_dirs(a, b, ignore_null=["pumpResults.*.control"])
    assert diff == 0
    assert "ignored pumpResults.*.control (null or absent): 2 values in 1 projects" in lines
    # a control result where the old dump has none is a difference (--ignore would hide it)
    write(b, "p", {"pumpResults": {"P1": {"speed": 1.0, "control": control}, "P2": {"speed": 1.0}}})
    lines, diff = compare.compare_dirs(a, b, ignore_null=["pumpResults.*.control"])
    assert diff == 1
    assert "ignored pumpResults.*.control (null or absent): 1 values in 1 projects" in lines
    _, diff = compare.compare_dirs(a, b, ["pumpResults.*.control"])
    assert diff == 0
    # null on one side, a value on the other; and equal values, compared as usual
    write(b, "p", {"pumpResults": {"P1": {"speed": 1.0}, "P2": {"speed": 1.0, "control": control}}})
    _, diff = compare.compare_dirs(a, b, ignore_null=["pumpResults.*.control"])
    assert diff == 1
    write(a, "p", {"pumpResults": {"P1": {"speed": 1.0, "control": control}}})
    write(b, "p", {"pumpResults": {"P1": {"speed": 1.0, "control": control}}})
    lines, diff = compare.compare_dirs(a, b, ignore_null=["pumpResults.*.control"])
    assert diff == 0
    assert "ignored pumpResults.*.control (null or absent): 0 values in 0 projects" in lines
    write(b, "p", {"pumpResults": {"P1": {"speed": 1.0, "control": {**control, "setpoint": 0.02}}}})
    _, diff = compare.compare_dirs(a, b, ignore_null=["pumpResults.*.control"])
    assert diff == 1
    # list items too
    write(a, "p", {"x": [1, None]})
    write(b, "p", {"x": [1, None]})
    _, diff = compare.compare_dirs(a, b, ignore_null=["x.*"])
    assert diff == 0
    write(b, "p", {"x": [1, 2]})
    _, diff = compare.compare_dirs(a, b, ignore_null=["x.*"])
    assert diff == 1


def test_compare_ignore_empty(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """--ignore-empty leaves out a map that is empty or absent on both sides (the result map
    every solved state gained with equipment, proposal equipment-pressure-drop.md §3.5), and
    compares it anywhere else: a non-empty value is still a difference."""
    a, b = tmp_path / "a", tmp_path / "b"
    item = {"flow": 0.01, "headLoss": 1.0, "rating": {"kind": "Kv", "value": 60.0}}
    write(a, "p", {"x": 1})  # a dump from before the map
    write(b, "p", {"x": 1, "equipmentResults": {}})
    _, diff = compare.compare_dirs(a, b)
    assert diff == 1
    lines, diff = compare.compare_dirs(a, b, ignore_empty=["equipmentResults"])
    assert diff == 0
    assert "ignored equipmentResults (empty or absent): 1 values in 1 projects" in lines
    # an equipment result where the old dump has none is a difference (--ignore would hide it)
    write(b, "p", {"x": 1, "equipmentResults": {"E1": item}})
    lines, diff = compare.compare_dirs(a, b, ignore_empty=["equipmentResults"])
    assert diff == 1
    assert "ignored equipmentResults (empty or absent): 0 values in 0 projects" in lines
    _, diff = compare.compare_dirs(a, b, ["equipmentResults"])
    assert diff == 0
    # empty on both sides (a map or a list) is left out; null is not empty, so it is compared
    write(a, "p", {"x": 1, "equipmentResults": {}})
    write(b, "p", {"x": 1, "equipmentResults": []})
    _, diff = compare.compare_dirs(a, b, ignore_empty=["equipmentResults"])
    assert diff == 0
    write(b, "p", {"x": 1, "equipmentResults": None})
    _, diff = compare.compare_dirs(a, b, ignore_empty=["equipmentResults"])
    assert diff == 1
    # equal values that are not empty compare as usual, and a changed one shows
    write(a, "p", {"equipmentResults": {"E1": item}})
    write(b, "p", {"equipmentResults": {"E1": item}})
    lines, diff = compare.compare_dirs(a, b, ignore_empty=["equipmentResults"])
    assert diff == 0
    assert "ignored equipmentResults (empty or absent): 0 values in 0 projects" in lines
    write(b, "p", {"equipmentResults": {"E1": {**item, "flow": 0.02}}})
    _, diff = compare.compare_dirs(a, b, ignore_empty=["equipmentResults"])
    assert diff == 1
    # a path matches at its depth only, with wildcards; a value under it is not empty
    write(a, "p", {"r": {"P1": {"c": []}, "P2": {}}})
    write(b, "p", {"r": {"P1": {}, "P2": {"c": {}}}})
    lines, diff = compare.compare_dirs(a, b, ignore_empty=["r.*.c"])
    assert diff == 0
    assert "ignored r.*.c (empty or absent): 2 values in 1 projects" in lines
    _, diff = compare.compare_dirs(a, b, ignore_empty=["r.c"])
    assert diff == 1
    write(b, "p", {"r": {"P1": {}, "P2": {"c": {"k": 1}}}})
    _, diff = compare.compare_dirs(a, b, ignore_empty=["r.*.c"])
    assert diff == 1
    # the command line
    write(b, "p", {"r": {"P1": {}, "P2": {"c": {}}}})
    with pytest.raises(SystemExit) as stop:
        compare.main([str(a), str(b), "--ignore-empty", "r.*.c"])
    assert stop.value.code == 0
    assert "ignored r.*.c (empty or absent): 2 values in 1 projects" in capsys.readouterr().out


def test_compare_the_orifice_proof_command(tmp_path: Path) -> None:
    """The corpus comparison of the orifice plate (proposal orifice-plate.md §3.9): ``compare A B
    --ignore-empty orificeResults --ignore methodVersion --ignore trace.methods.methodVersion``
    leaves out the new empty map and the version, in both modes, while an orifice result the old
    dump lacks, a changed value or an equipment map left empty on one side only is a difference;
    each ignore's count is printed."""
    a, b = tmp_path / "a", tmp_path / "b"
    methods = {"methodVersion": "1.3.0", "sections": []}
    old: dict[str, Any] = {
        "methodVersion": "1.3.0",
        "equipmentResults": {},
        "trace": {"methods": methods},
    }
    new = copy.deepcopy(old)
    new["methodVersion"] = new["trace"]["methods"]["methodVersion"] = "1.4.0"
    new["orificeResults"] = {}
    write(a, "p", old)
    write(b, "p", new)
    ignore = ["methodVersion", "trace.methods.methodVersion"]
    for tolerances in (None, compare.DEFAULT_SETTINGS):
        _, diff = compare.compare_dirs(a, b, ignore, tolerances=tolerances)
        assert diff == 1  # the new map shows without --ignore-empty
        lines, diff = compare.compare_dirs(
            a, b, ignore, tolerances=tolerances, ignore_empty=["orificeResults"]
        )
        assert diff == 0
        assert "ignored orificeResults (empty or absent): 1 values in 1 projects" in lines
        assert "ignored methodVersion: 1 values in 1 projects" in lines
        assert "ignored trace.methods.methodVersion: 1 values in 1 projects" in lines
    item = {"flow": 0.0174, "headLoss": 6.886, "pressureLoss": 67393.3, "beta": 0.5}
    write(b, "p", {**new, "orificeResults": {"OR1": item}})
    lines, diff = compare.compare_dirs(a, b, ignore, ignore_empty=["orificeResults"])
    assert diff == 1
    assert "ignored orificeResults (empty or absent): 0 values in 0 projects" in lines
    write(a, "p", {**old, "orificeResults": {"OR1": item}})
    write(b, "p", {**new, "orificeResults": {"OR1": {**item, "pressureLoss": 67393.4}}})
    _, diff = compare.compare_dirs(a, b, ignore, ignore_empty=["orificeResults"])
    assert diff == 1
    write(b, "p", {**new, "orificeResults": {"OR1": item}, "equipmentResults": []})
    _, diff = compare.compare_dirs(a, b, ignore, ignore_empty=["orificeResults"])
    assert diff == 1  # each path is left out only where it is named
    _, diff = compare.compare_dirs(
        a, b, ignore, ignore_empty=["orificeResults", "equipmentResults"]
    )
    assert diff == 0


# --------------------------------------------------------------------------- missing results
# A pump or valve without a result is skipped by every other check (state 'isolated'), so
# ``checks.missing_result_problems`` holds it to the rule for when one has none (SDD §4.10, TSD
# §5.4). Small networks of random test inputs, solved in the fuzz networks' friction mode
# ('swamee_jain', whose f formula the energy check uses), then their results edited: a result
# deleted (``missing_result_check.without``) must be reported, and the results the rule leaves
# out must not be.

LINE = [custom_pipe(0.05, 100.0, 1.0e-5)]


def solved(
    components: list[Component], connections: list[PipeConnection]
) -> tuple[Project, SolvedState]:
    project = make_project(
        "t",
        "t",
        WATER,
        components,
        connections,
        friction_method="swamee_jain",
        pump_library=[CURVE],
    )
    result = solve_project(project)
    assert result.converged, result.convergence.message
    return project, result


def isolated(project: Project, result: SolvedState) -> set[str]:
    """The pumps and valves without a result (``checks.our_states``: 'isolated')."""
    return {k for k, v in ck.our_states(project, result).items() if v == "isolated"}


def flowing_network() -> tuple[Project, SolvedState]:
    """R1 → P1 → T1 → V1 → R2 and T1 → R3 carry flow; R1 → IV1 (isolated) → P2 → V2 → PL1 is
    closed off, and so is P3 (off) → PL2, a dead end behind a pump that is off."""
    components: list[Component] = [
        reservoir("R1", 0.0, 5.0, ports=("port_1", "port_2", "port_3")),
        reservoir("R2", 0.0, 10.0),
        reservoir("R3", 0.0, 12.0),
        pump("P1", 0.0, "PC"),
        ideal_tee("T1", 0.0),
        isolation_valve("V1", 0.0, "gate"),
        isolation_valve("IV1", 0.0, "gate", status="isolated"),
        pump("P2", 0.0, "PC"),
        isolation_valve("V2", 0.0, "gate"),
        plug("PL1", 0.0),
        pump("P3", 0.0, "PC", status="off"),
        plug("PL2", 0.0),
    ]
    connections = [
        connect("C1", "R1:port_1", "P1:suction", LINE),
        connect("C2", "P1:discharge", "T1:run_inlet", LINE),
        connect("C3", "T1:run_outlet", "V1:inlet", LINE),
        connect("C4", "V1:outlet", "R2:port_1", LINE),
        connect("C5", "T1:branch", "R3:port_1", LINE),
        connect("C6", "R1:port_2", "IV1:inlet", LINE),
        connect("C7", "IV1:outlet", "P2:suction", LINE),
        connect("C8", "P2:discharge", "V2:inlet", LINE),
        connect("C9", "V2:outlet", "PL1:port_1", LINE),
        connect("C10", "R1:port_3", "P3:suction", LINE),
        connect("C11", "P3:discharge", "PL2:port_1", LINE),
    ]
    return solved(components, connections)


def test_dropped_results_where_flow_runs_are_reported() -> None:
    project, result = flowing_network()
    # the results the rule leaves out: closed off (P2, V2), at a closed-off section (IV1), and a
    # pump that is off beside one (P3)
    assert isolated(project, result) == {"IV1", "P2", "V2", "P3"}
    assert ck.self_check(project, result) == []
    pumped, passed = result.link_results["C1"].flow, result.link_results["C3"].flow
    assert result.pump_results["P1"].operating_flow == pumped > 0.0
    assert result.valve_results["V1"].flow == passed > 0.0
    p1 = f"no result for P1: it carries {pumped:.6g} m³/s; both its ports have heads"
    v1 = f"no result for V1: it carries {passed:.6g} m³/s; both its ports have heads"
    assert ck.self_check(project, without(result, "P1")) == [p1]
    assert ck.self_check(project, without(result, "V1")) == [v1]
    assert ck.self_check(project, without(result, "P1", "V1")) == [p1, v1]


def test_missing_results_need_the_flag_that_says_why() -> None:
    project, result = flowing_network()
    unflagged = result.model_copy(
        update={"flags": [f for f in result.flags if f.code != "ISOLATED_SECTION"]}
    )
    problems = ck.self_check(project, unflagged)
    assert [p.split(":")[0] for p in problems] == [
        f"no result for {i}" for i in ("IV1", "P2", "V2", "P3")
    ]
    assert all("no ISOLATED_SECTION flag names it" in p for p in problems)


def pump_loop(stub: Literal["active", "isolated"]) -> tuple[Project, SolvedState]:
    """R0 → IV1 (isolated) → T1, and the loop T1 → PU1 → T2 → V9 → T1 that PU1 drives with no
    fixed head (a floating section, UNDETERMINED_PRESSURE); the stub T2 → V8 → PL1 carries no
    flow, joined to the loop by V8 open (``stub`` 'active') or closed off by it ('isolated')."""
    components: list[Component] = [
        reservoir("R0", 0.0, 10.0),
        isolation_valve("IV1", 0.0, "gate", status="isolated"),
        ideal_tee("T1", 0.0),
        pump("PU1", 0.0, "PC"),
        ideal_tee("T2", 0.0),
        isolation_valve("V8", 0.0, "gate", status=stub),
        plug("PL1", 0.0),
        isolation_valve("V9", 0.0, "gate"),
    ]
    connections = [
        connect("L1", "R0:port_1", "IV1:inlet", LINE),
        connect("L2", "IV1:outlet", "T1:run_inlet", LINE),
        connect("L3", "T1:run_outlet", "PU1:suction", LINE),
        connect("L4", "PU1:discharge", "T2:run_inlet", LINE),
        connect("L5", "T2:run_outlet", "V8:inlet", LINE),
        connect("L6", "V8:outlet", "PL1:port_1", LINE),
        connect("L7", "T2:branch", "V9:inlet", LINE),
        connect("L8", "V9:outlet", "T1:branch", LINE),
    ]
    return solved(components, connections)


@pytest.mark.parametrize("stub", ["active", "isolated"])
def test_dropped_results_in_a_floating_section_are_reported(
    stub: Literal["active", "isolated"],
) -> None:
    project, result = pump_loop(stub)
    assert set(result.node_results) == {"R0:port_1", "IV1:inlet"}  # the loop has no heads
    # IV1 is between the loop and a head; V8 closed sits between it and a closed-off stub
    assert isolated(project, result) == ({"IV1"} if stub == "active" else {"IV1", "V8"})
    assert ck.self_check(project, result) == []
    q = result.link_results["L3"].flow
    assert q > 0.0
    for cid in ("PU1", "V9"):
        assert ck.self_check(project, without(result, cid)) == [
            f"no result for {cid}: it carries {q:.6g} m³/s; both its ports are in one floating"
            " section"
        ]


def test_a_dropped_result_at_rest_in_a_floating_section_is_reported() -> None:
    """V8 open carries no flow, but its stub is part of the floating section: its result
    (relative heads) is reported. Without it, the stub looks closed off, which the flags deny."""
    project, result = pump_loop("active")
    assert result.valve_results["V8"].flow == 0.0
    assert ck.self_check(project, without(result, "V8")) == [
        "no result for V8: V8:outlet is in a section without flow, and no ISOLATED_SECTION flag"
        " names it"
    ]


def test_a_dropped_dead_headed_pump_is_reported() -> None:
    """R1 → PU → CV → RH with RH above PU's shutoff head: PU is held at no flow and CV closed,
    the section between them closed off; PU is reported dead-headed (TSD §5.4), CV not."""
    project, result = solved(
        [
            reservoir("R1", 0.0, 5.0),
            reservoir("RH", 0.0, A + 20.0),
            pump("PU", 0.0, "PC"),
            check_valve("CV", 0.0, "check"),
        ],
        [
            connect("C1", "R1:port_1", "PU:suction", LINE),
            connect("C2", "PU:discharge", "CV:inlet", LINE),
            connect("C3", "CV:outlet", "RH:port_1", LINE),
        ],
    )
    assert result.pump_results["PU"].status == "no_flow"
    assert isolated(project, result) == {"CV"}
    assert ck.self_check(project, result) == []
    assert ck.self_check(project, without(result, "PU")) == [
        "no result for PU: it is on with PU:discharge closed off and its other side at a head"
    ]
