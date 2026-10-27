"""The equipment element (docs/proposals/equipment-pressure-drop.md §2-§5, §7.6): its law, the
builder, the topology issue, zero flow, closed-off and floating sections, the flags, the trace,
the methods summary and the version.

Expected values come from the definitions written out here (h_r = ΔP_r/(ρ_r g), c = h_r/Q_r²;
a Cv or Kv as K = 1.6e9 D⁴/Kv² on any bore), from fluids' converters called directly, and from
the same network with the element replaced by a gate valve of the equivalent K (the valve path
is independent of the equipment code), never from the equipment code itself. Every rating,
length, level and fluid below is a made-up test input.
"""

import math
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fluids.constants import bar, g, gallon, hour, minute, psi
from pydantic import ValidationError
from scipy.constants import foot

from opensolve_pipe.main import app
from opensolve_pipe.models.components import Equipment, RatedFlowCoefficient
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import Flag, SolvedState
from opensolve_pipe.services.fluids import fluid_properties
from opensolve_pipe.services.solver import solve_project, status, system_curve
from opensolve_pipe.services.solver.builder import build_network
from opensolve_pipe.services.solver.elements import PipeSegment, QuadraticLossLaw, segment_state
from opensolve_pipe.services.solver.equipment import COEFFICIENT_SOURCE, equipment_law
from opensolve_pipe.services.solver.errors import TopologyError
from opensolve_pipe.services.solver.methods import (
    DARBY,
    EQUIPMENT_ASSUMPTION,
    ISA_75,
    methods_summary,
)
from opensolve_pipe.services.solver.network import LinkKind
from opensolve_pipe.services.solver.status import Status
from opensolve_pipe.services.solver.valves import k_from_coefficient

from .helpers import connection, custom_fluid, make_project, plug, project_dict, reservoir, tee

POINT: dict[str, Any] = {
    "kind": "point",
    "pressureLoss": 50000.0,
    "flow": 0.015,
    "density": 999.102621,
}
"""E1 of the proposal's cases (§7.1): 50 kPa at 15 L/s, rated on water at 15 °C (test input)."""
CV: dict[str, Any] = {"kind": "Cv", "value": 90.0}
KV: dict[str, Any] = {"kind": "Kv", "value": 60.0}
D = 0.1023
"""m: the pipes' inner diameter (test input)."""
FLUIDS_WATER = 999.29744568
"""kg/m³: the water fluids' Kv_to_K is defined on (its docstring: 60 °F, IAPWS-95)."""


def _flags(state: SolvedState, code: str, element: str | None = None) -> list[Flag]:
    return [
        f for f in state.flags if f.code == code and (element is None or f.component_id == element)
    ]


def _area(d: float) -> float:
    return math.pi * d * d / 4.0


def equipment(
    cid: str,
    rating: dict[str, Any],
    *,
    elevation: float = 3.0,
    inlet: float | None = None,
    outlet: float | None = None,
) -> dict[str, Any]:
    ports: list[dict[str, Any]] = [
        {"id": "inlet", "nominalSize": 0.1},
        {"id": "outlet", "nominalSize": 0.1},
    ]
    if inlet is not None:
        ports[0]["elevation"] = inlet
    if outlet is not None:
        ports[1]["elevation"] = outlet
    return {
        "type": "equipment",
        "id": cid,
        "name": cid,
        "elevation": elevation,
        "ports": ports,
        "rating": rating,
    }


def gate(cid: str, resistance: dict[str, Any], *, elevation: float = 3.0) -> dict[str, Any]:
    return {
        "type": "valve",
        "valveType": "gate",
        "id": cid,
        "name": cid,
        "elevation": elevation,
        "status": "active",
        "resistance": resistance,
        "ports": [{"id": "inlet", "nominalSize": 0.1}, {"id": "outlet", "nominalSize": 0.1}],
    }


def line_dict(
    element: dict[str, Any],
    *,
    h1: float = 12.0,
    h2: float = 1.0,
    d_in: float = D,
    d_out: float = D,
    **kw: Any,
) -> dict[str, Any]:
    """R1 (level h1) -> L1 (60 m) -> element -> L2 (40 m) -> R2 (level h2), both at z = 0."""
    eid = element["id"]
    comps = [reservoir("R1", level=h1), element, reservoir("R2", level=h2)]
    conns = [
        connection("L1", ("R1", "port_1"), (eid, "inlet"), length=60.0, diameter=d_in),
        connection("L2", (eid, "outlet"), ("R2", "port_1"), length=40.0, diameter=d_out),
    ]
    return project_dict(comps, conns, **kw)


def line(element: dict[str, Any], **kw: Any) -> Project:
    return Project.model_validate(line_dict(element, **kw))


def point_c(rating: dict[str, Any]) -> float:
    """c from the definition, in the proposal's order (decision 5)."""
    rated_head = rating["pressureLoss"] / (rating["density"] * g)
    return float(rated_head / (rating["flow"] * rating["flow"]))


def coefficient_c(kind: str, value: float) -> float:
    """c = K/(2 g A²) with K = 1.6e9 D⁴/Kv² (Kv = Cv/1.1560992283536566): 1.28e10/(π² g Kv²)."""
    kv = value / 1.1560992283536566 if kind == "Cv" else value
    return 1.28e10 / (math.pi**2 * g * kv * kv)


# --------------------------------------------------------------------------- the law


@pytest.mark.parametrize("q", [-0.03, -1.0e-4, 0.0, 1.0e-4, 0.02])
def test_the_law_is_odd_with_a_zero_slope_at_zero_flow(q: float) -> None:
    c = 22680.713484384312
    law = QuadraticLossLaw(c)
    h, slope = law.evaluate(q)
    assert h == c * q * abs(q)
    assert slope == 2.0 * c * abs(q)
    assert law.evaluate(-q) == (-h, slope)
    assert QuadraticLossLaw(c).evaluate(0.0) == (0.0, 0.0)


@pytest.mark.parametrize("c", [0.0, -1.0, math.inf, math.nan])
def test_the_law_needs_a_finite_positive_c(c: float) -> None:
    with pytest.raises(ValueError, match="finite c > 0"):
        QuadraticLossLaw(c)


# --------------------------------------------------------------------------- the builder


def _built(project: Project) -> Any:
    return build_network(project, fluid_properties(project.fluid))


def test_the_builder_adds_one_link_with_c_of_the_rated_point() -> None:
    built = _built(line(equipment("E1", POINT)))
    data = built.equipment["E1"]
    link = built.network.links[data.link_index]
    assert link.kind is LinkKind.EQUIPMENT
    assert (link.component_id, link.port_id) == ("E1", None)
    assert built.network.nodes[link.start].key == "E1:inlet" == data.inlet
    assert built.network.nodes[link.end].key == "E1:outlet" == data.outlet
    assert isinstance(link.law, QuadraticLossLaw)
    # Computed once, in the proposal's order: bit for bit.
    assert link.law.coefficient == data.law.coefficient == point_c(POINT)
    assert data.law.rated_head == POINT["pressureLoss"] / (POINT["density"] * g)
    assert (data.law.rated_pressure, data.law.rated_flow, data.law.rating_density) == (
        POINT["pressureLoss"],
        POINT["flow"],
        POINT["density"],
    )
    # The proposal's E1: h_r = 5.10316053 m, c = 22,680.7135 s²/m⁵ (§7.1).
    assert data.law.rated_head == pytest.approx(5.10316053, rel=1e-9)
    assert data.law.coefficient == pytest.approx(22680.7135, rel=1e-9)
    # 1 ft/s in the inlet pipe (EPANET 2.2 initlinkflow)
    assert link.initial_flow == foot * data.inlet_pipe.segment.area
    assert link.initial_flow == pytest.approx(foot * _area(D), rel=1e-15)
    assert (data.inlet_pipe.segment.diameter, data.outlet_pipe.segment.diameter) == (D, D)
    # A project without equipment has none.
    assert _built(line(gate("V1", {"kind": "K", "value": 1.0}))).equipment == {}


@pytest.mark.parametrize(
    "rating", [CV, KV, {"kind": "Cv", "value": 1.0e-3}, {"kind": "Kv", "value": 1.0e7}]
)
def test_a_cv_or_kv_gives_the_c_of_its_definition_and_of_the_valve_path(
    rating: dict[str, Any],
) -> None:
    """Decision 5, §3.1: c at a 1 m bore equals the closed form and the valve path (K on the
    bore, then K/(2 g A²)) on every bore to round-off, at 2e-15 relative (the measured maxima are
    5.3e-16 and 8.8e-16; neither is bit-exact)."""
    built = _built(line(equipment("E1", rating)))
    law = built.equipment["E1"].law
    c = law.coefficient
    assert c == pytest.approx(coefficient_c(rating["kind"], rating["value"]), rel=2e-15)
    model = Equipment.model_validate(equipment("E1", rating)).rating
    assert isinstance(model, RatedFlowCoefficient)
    for bore in (0.0127, 0.05, D, 0.3, 1.0, 2.5):
        k = k_from_coefficient(model, bore)[0]
        assert c == pytest.approx(k / (2.0 * g * _area(bore) ** 2), rel=2e-15), bore
    # Its rated point: ΔP₁ = 1 psi at Cv US gpm (1 bar at Kv m³/h) on fluids' water.
    dp1, per_unit = (psi, gallon / minute) if rating["kind"] == "Cv" else (bar, 1.0 / hour)
    assert law.rated_pressure == dp1
    assert law.rated_flow == rating["value"] * per_unit
    assert law.rating_density == pytest.approx(FLUIDS_WATER, rel=1e-9)
    assert law.rated_head == pytest.approx(dp1 / (FLUIDS_WATER * g), rel=1e-9)


BAD_RATINGS = {
    "point 1e-300": ({**POINT, "flow": 1.0e-300, "density": 1.0e-300}, ZeroDivisionError),
    "Cv 1e-170": ({"kind": "Cv", "value": 1.0e-170}, ZeroDivisionError),
    "Kv 1e-160": ({"kind": "Kv", "value": 1.0e-160}, OverflowError),
    "Cv 2e-150": ({"kind": "Cv", "value": 2.0e-150}, None),  # c = inf, no exception
    "point underflow": ({**POINT, "pressureLoss": 5.0e-324, "density": 3.0e4}, None),  # c = 0
}


@pytest.mark.parametrize("name", list(BAD_RATINGS))
def test_a_rating_the_solver_cannot_represent_is_a_topology_issue(name: str) -> None:
    """Decision 10: inside the schema's bounds, a rating whose c is not a finite positive
    double, or whose computation divides by zero or overflows, is EQUIPMENT_RATING_OUT_OF_RANGE,
    listed after the other issues (here an unconnected plug and a valve's Cv of 1e-170)."""
    rating, raised = BAD_RATINGS[name]
    model = Equipment.model_validate(equipment("E1", rating)).rating
    if raised is not None:
        with pytest.raises(raised):
            equipment_law(model, g)
    else:
        c = equipment_law(model, g).coefficient
        assert not (math.isfinite(c) and c > 0.0)
    comps = [
        reservoir("R1", level=12.0),
        gate("V1", {"kind": "Cv", "value": 1.0e-170}),
        equipment("E1", rating),
        reservoir("R2", level=1.0),
        plug("P9"),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("V1", "inlet")),
        connection("L2", ("V1", "outlet"), ("E1", "inlet")),
        connection("L3", ("E1", "outlet"), ("R2", "port_1")),
    ]
    with pytest.raises(TopologyError) as caught:
        solve_project(make_project(comps, conns))
    codes = [i.code for i in caught.value.issues]
    assert codes == [
        "UNCONNECTED_PORT",
        "VALVE_RESISTANCE_OUT_OF_RANGE",
        "EQUIPMENT_RATING_OUT_OF_RANGE",
    ]
    found = caught.value.issues[-1]
    assert (found.component_ids, found.connection_ids) == (["E1"], [])
    assert found.message.startswith("equipment 'E1': a rating of ")
    assert "not a finite positive floating-point number" in found.message


def test_the_smallest_representable_coefficients_still_build() -> None:
    """A Cv or Kv of 1e-149 gives a finite c (2e-150 already gives c = inf, §1.2 decision 10)."""
    for kind in ("Cv", "Kv"):
        built = _built(line(equipment("E1", {"kind": kind, "value": 1.0e-149})))
        assert math.isfinite(built.equipment["E1"].law.coefficient)


# --------------------------------------------------------------------------- the model


def test_the_model_publishes_its_ports_and_refuses_a_k_without_quoting_it() -> None:
    schema = Equipment.model_json_schema()
    assert schema["x-port-ids"] == ["inlet", "outlet"]
    assert schema["x-port-roles"] == {"inlet": "inlet", "outlet": "outlet"}
    with pytest.raises(ValidationError) as caught:
        Equipment.model_validate(equipment("E1", {"kind": "K", "value": 12345.678}))
    [error] = caught.value.errors()
    assert error["type"] == "invalid_rating"
    # The API's VALIDATION_ERROR shows the type, location and message, never the input.
    assert error["msg"] == "unknown rating kind (expected 'point', 'Cv' or 'Kv')"
    assert "12345.678" not in error["msg"]
    with pytest.raises(ValidationError) as caught:
        Equipment.model_validate(
            equipment("E1", {k: v for k, v in POINT.items() if k != "density"})
        )
    assert [e["type"] for e in caught.value.errors()] == ["missing"]
    with pytest.raises(ValidationError):
        Equipment.model_validate(equipment("E1", {"kind": "Cv"}))


# --------------------------------------------------------------------------- solving


def _node_heads(state: SolvedState) -> dict[str, float]:
    return {k: n.egl for k, n in state.node_results.items()}


@pytest.mark.parametrize(
    ("rating", "resistance"),
    [
        (POINT, {"kind": "K", "value": 2.0 * g * _area(D) ** 2 * point_c(POINT)}),
        (CV, CV),
        (KV, KV),
    ],
)
def test_the_element_solves_as_a_gate_valve_of_the_same_loss(
    rating: dict[str, Any], resistance: dict[str, Any]
) -> None:
    """§7.3's unit test: the element gives the flows and heads of a gate valve with K = K_E on the
    inlet pipe (a rated point) or with the same Cv or Kv, to about 1e-12 relative."""
    state = solve_project(line(equipment("E1", rating)))
    valve = solve_project(line(gate("E1", resistance)))
    assert state.converged
    assert valve.converged
    result, reference = state.equipment_results["E1"], valve.valve_results["E1"]
    assert result.flow == pytest.approx(reference.flow, rel=1e-12)
    assert result.head_loss == pytest.approx(reference.head_loss, rel=1e-12)
    assert result.pressure_drop == pytest.approx(reference.pressure_drop, rel=1e-12)
    for key, head in _node_heads(valve).items():
        assert _node_heads(state)[key] == pytest.approx(head, rel=1e-12), key
    for cid, link in valve.link_results.items():
        assert state.link_results[cid].flow == pytest.approx(link.flow, rel=1e-12)
    assert state.valve_results == {}
    assert valve.equipment_results == {}


def test_the_result_scales_the_rating_with_the_flow_squared_and_density() -> None:
    """ρ g h = ΔP_r (ρ/ρ_r)(Q/Q_r)², the flow ratio Q/Q_r, the rating echoed (§2.2)."""
    rho = 1100.0
    state = solve_project(line(equipment("E1", POINT), fluid=custom_fluid(rho, 1.0e-3)))
    result = state.equipment_results["E1"]
    q = result.flow
    assert result.flow_ratio == q / POINT["flow"]
    assert result.head_loss == pytest.approx(point_c(POINT) * q * abs(q), rel=1e-9)
    assert result.pressure_loss == rho * g * result.head_loss
    expected = POINT["pressureLoss"] * (rho / POINT["density"]) * (q / POINT["flow"]) ** 2
    assert result.pressure_loss == pytest.approx(expected, rel=1e-9)
    assert result.rating.model_dump(mode="json", by_alias=True) == POINT
    cv = solve_project(line(equipment("E1", CV))).equipment_results["E1"]
    assert cv.flow_ratio is None
    assert cv.rating.model_dump(mode="json", by_alias=True) == CV


def test_the_static_drop_holds_the_elevation_and_velocity_terms() -> None:
    """§3.3: Δp_static = ρ g h + ρ g (z_out − z_in) + ρ (v_out² − v_in²)/2, with the outlet port
    2 m up and the outlet pipe one size down (the proposal's equipment_ports_differ shape)."""
    element = equipment("E1", POINT, elevation=20.0, inlet=20.0, outlet=22.0)
    state = solve_project(line(element, h1=30.0, h2=2.0, d_out=0.0779))
    result = state.equipment_results["E1"]
    rho, q = 998.0, result.flow
    v_in, v_out = q / _area(D), q / _area(0.0779)
    identity = result.pressure_loss + rho * g * 2.0 + 0.5 * rho * (v_out**2 - v_in**2)
    assert result.pressure_drop == pytest.approx(identity, rel=1e-12)
    assert result.pressure_drop > result.pressure_loss
    nodes = state.node_results
    static = nodes["E1:inlet"].pressure - nodes["E1:outlet"].pressure
    assert result.pressure_drop == pytest.approx(static, rel=1e-14)  # as a valve's, to round-off
    assert nodes["E1:outlet"].elevation == 22.0


def test_zero_flow_between_equal_heads_and_at_a_dead_end() -> None:
    """Decision 7: the zero-slope law converges at zero flow (the Jacobian floor), between equal
    heads and on a dead end to a plug, and is not flagged."""
    still = solve_project(line(equipment("E1", POINT), h1=5.0, h2=5.0))
    assert still.converged
    result = still.equipment_results["E1"]
    assert (result.flow, result.flow_ratio) == (0.0, 0.0)
    assert abs(result.head_loss) < 1.0e-9
    assert not _flags(still, "CORRELATION_OUT_OF_RANGE")
    comps = [reservoir("R1", level=5.0), equipment("E1", CV), plug("P1")]
    conns = [
        connection("L1", ("R1", "port_1"), ("E1", "inlet")),
        connection("L2", ("E1", "outlet"), ("P1", "port_1")),
    ]
    dead = solve_project(make_project(comps, conns))
    assert dead.converged
    assert dead.equipment_results["E1"].flow == 0.0
    assert dead.equipment_results["E1"].head_loss == pytest.approx(0.0, abs=1.0e-9)
    assert not _flags(dead, "CORRELATION_OUT_OF_RANGE")


def test_an_element_closed_off_between_isolated_valves_has_no_result() -> None:
    comps = [
        reservoir("R1", level=12.0),
        {**gate("V1", {"kind": "K", "value": 0.2}), "status": "isolated"},
        equipment("E1", POINT),
        {**gate("V2", {"kind": "K", "value": 0.2}), "status": "isolated"},
        reservoir("R2", level=1.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("V1", "inlet")),
        connection("L2", ("V1", "outlet"), ("E1", "inlet")),
        connection("L3", ("E1", "outlet"), ("V2", "inlet")),
        connection("L4", ("V2", "outlet"), ("R2", "port_1")),
    ]
    state = solve_project(make_project(comps, conns))
    assert state.converged
    assert "E1" not in state.equipment_results
    [isolated] = _flags(state, "ISOLATED_SECTION")
    assert "E1" in str(isolated.details["componentIds"])
    trace = state.trace.elements["E1"]
    assert any(
        n.startswith("No result values: this element lies in a section closed off")
        for n in trace.notes
    )
    assert not any(v.name.startswith("Flow Q") for v in trace.intermediates)


def test_an_element_in_a_floating_pump_loop_has_its_flow_and_head_loss() -> None:
    """§2.2: a pump loop behind a closed valve circulates through the element; its flow and head
    differences are determined (UNDETERMINED_PRESSURE), its port pressures are not."""
    pump = {
        "type": "pump",
        "id": "PU",
        "name": "PU",
        "elevation": 0.0,
        "curveId": "C1",
        "ports": [{"id": "suction", "nominalSize": 0.1}, {"id": "discharge", "nominalSize": 0.1}],
    }
    comps = [
        reservoir("R1", level=10.0),
        {**gate("V", {"kind": "K", "value": 0.2}, elevation=0.0), "status": "isolated"},
        tee("T1"),
        pump,
        equipment("E1", POINT, elevation=0.0),
        tee("T2"),
        plug("P"),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("V", "inlet")),
        connection("L2", ("V", "outlet"), ("T1", "run_inlet")),
        connection("L3", ("T1", "run_outlet"), ("PU", "suction"), length=50.0),
        connection("L4", ("PU", "discharge"), ("E1", "inlet"), length=25.0),
        connection("L7", ("E1", "outlet"), ("T2", "run_inlet"), length=25.0),
        connection("L5", ("T2", "run_outlet"), ("P", "port_1")),
        connection("L6", ("T2", "branch"), ("T1", "branch"), length=400.0),
    ]
    curve = {
        "id": "C1",
        "name": "test pump",
        "points": [{"flow": q, "head": h} for q, h in ((0.0, 30.0), (0.01, 25.0), (0.02, 20.0))],
    }
    state = solve_project(make_project(comps, conns, pump_library=[curve]))
    assert state.converged
    [flag] = _flags(state, "UNDETERMINED_PRESSURE")
    assert "E1" in str(flag.details["componentIds"])
    result = state.equipment_results["E1"]
    q = state.pump_results["PU"].operating_flow
    assert q > 0.0
    assert result.flow == pytest.approx(q, rel=1e-12)
    assert result.head_loss == pytest.approx(point_c(POINT) * q * q, rel=1e-9)
    assert result.pressure_loss == 998.0 * g * result.head_loss
    assert result.pressure_drop == pytest.approx(result.pressure_loss, rel=1e-9)
    assert "E1:inlet" not in state.node_results
    assert "E1:outlet" not in state.node_results
    notes = state.trace.elements["E1"].notes
    assert any(n.startswith("Pressure level undetermined (UNDETERMINED_PRESSURE)") for n in notes)


def test_a_system_curve_through_an_element_adds_its_c_q_squared() -> None:
    """§7.1's system curve: pump -> element -> reservoir gives H_sys(Q) = Δz + Σ h_line(Q) +
    c Q² at every point (the pipes' losses from the friction law of each segment)."""
    pump = {
        "type": "pump",
        "id": "P1",
        "name": "P1",
        "elevation": 0.0,
        "curveId": "C1",
        "ports": [{"id": "suction", "nominalSize": 0.1}, {"id": "discharge", "nominalSize": 0.1}],
    }
    curve = {
        "id": "C1",
        "name": "test pump",
        "points": [{"flow": q, "head": h} for q, h in ((0.0, 40.0), (0.02, 35.0), (0.04, 20.0))],
    }
    comps = [reservoir("R1", level=2.0), pump, equipment("E1", POINT, elevation=0.0)]
    comps.append(reservoir("R2", level=12.0))
    lengths = (5.0, 30.0, 20.0)
    conns = [
        connection("L1", ("R1", "port_1"), ("P1", "suction"), length=lengths[0]),
        connection("L2", ("P1", "discharge"), ("E1", "inlet"), length=lengths[1]),
        connection("L3", ("E1", "outlet"), ("R2", "port_1"), length=lengths[2]),
    ]
    project = make_project(comps, conns, pump_library=[curve])
    points = system_curve(project, "P1", flow_min=0.0, flow_max=0.03, num_points=4).points
    nu = 1.0e-3 / 998.0
    for point in points:
        q = point.flow
        lines = sum(
            segment_state(PipeSegment(n, 0.1, 4.5e-5, _area(0.1), nu, g), q, "colebrook").head_loss
            for n in lengths
        )
        assert point.head == pytest.approx(10.0 + lines + point_c(POINT) * q * q, rel=1e-12)


# --------------------------------------------------------------------------- flags


REVERSE = (
    "equipment 'E1': the flow runs from outlet to inlet; its rating is for inlet → outlet flow, "
    "and the loss is taken as for forward flow at the same flow rate"
)


@pytest.mark.parametrize("rating", [POINT, CV])
def test_reverse_flow_is_flagged_without_numbers(rating: dict[str, Any]) -> None:
    """Decision 6: the symmetric law, a CORRELATION_OUT_OF_RANGE warning whose message has no
    numbers; details: the flow, and the rated flow for a rated point."""
    forward = solve_project(line(equipment("E1", rating)))
    reverse = solve_project(line(equipment("E1", rating), h1=1.0, h2=12.0))
    assert not _flags(forward, "CORRELATION_OUT_OF_RANGE")
    q = reverse.equipment_results["E1"].flow
    assert q < 0.0
    assert q == pytest.approx(-forward.equipment_results["E1"].flow, rel=1e-12)
    [flag] = _flags(reverse, "CORRELATION_OUT_OF_RANGE", "E1")
    assert (flag.severity, flag.message) == ("warning", REVERSE)
    expected: dict[str, Any] = {"flow": q}
    if rating["kind"] == "point":
        expected["ratedFlow"] = POINT["flow"]
    assert flag.details == expected
    notes = reverse.trace.elements["E1"].notes
    assert any(n.startswith("Reverse flow: Q = ") for n in notes)
    assert any(
        n.startswith("Flag CORRELATION_OUT_OF_RANGE (warning): equipment 'E1'") for n in notes
    )


def _re(q: float, d: float, nu: float) -> float:
    return abs(q) * d / (_area(d) * nu)


@pytest.mark.parametrize(("d_in", "d_out", "side"), [(0.2, 0.1, "inlet"), (0.1, 0.2, "outlet")])
def test_laminar_flow_in_a_connected_pipe_is_flagged_with_the_lower_re(
    d_in: float, d_out: float, side: str
) -> None:
    """Decision 9: Re < 2000 in either connected pipe's end segment, the lower Re of the two (the
    larger bore), as a valve's Cv or Kv; a liquid of 1 Pa·s (test input)."""
    rho, mu = 1200.0, 1.0
    state = solve_project(
        line(
            equipment("E1", KV),
            h1=20.0,
            h2=10.0,
            d_in=d_in,
            d_out=d_out,
            fluid=custom_fluid(rho, mu),
        )
    )
    assert state.converged
    q = state.equipment_results["E1"].flow
    re = _re(q, max(d_in, d_out), mu / rho)
    assert 0.0 < re < 2000.0
    [flag] = _flags(state, "CORRELATION_OUT_OF_RANGE", "E1")
    assert flag.severity == "warning"
    assert flag.message == (
        "equipment 'E1': its rating is scaled at constant K, the turbulent-flow law of "
        f"ISA-75.01.01, but the flow in its {side} pipe is laminar (Re = {re:.0f}); the loss "
        "is likely underestimated"
    )
    assert flag.details["reynoldsNumber"] == pytest.approx(re, rel=1e-12)
    notes = state.trace.elements["E1"].notes
    assert any(n.startswith(f"Laminar flow in its {side} pipe: Re = ") for n in notes)


def test_reverse_and_laminar_flow_are_flagged_together() -> None:
    state = solve_project(
        line(equipment("E1", POINT), h1=10.0, h2=20.0, fluid=custom_fluid(1200.0, 1.0))
    )
    flags = _flags(state, "CORRELATION_OUT_OF_RANGE", "E1")
    assert len(flags) == 2
    assert flags[0].message == REVERSE
    assert "laminar" in flags[1].message


# --------------------------------------------------------------------------- trace


def _values(state: SolvedState, element: str) -> dict[str, float]:
    return {v.name: v.value for v in state.trace.elements[element].intermediates}


def test_the_trace_of_a_rated_point() -> None:
    element = equipment("E1", POINT, elevation=20.0, inlet=20.0, outlet=22.0)
    state = solve_project(line(element, h1=30.0, h2=2.0, d_out=0.0779))
    trace = state.trace.elements["E1"]
    assert trace.element_type == "equipment"
    inputs = {i.name: i for i in trace.inputs}
    rating = [inputs[n] for n in inputs if n.startswith("Rated ")]
    assert [(i.value, i.source) for i in rating] == [
        (POINT["pressureLoss"], "user"),
        (POINT["flow"], "user"),
        (POINT["density"], "user"),
    ]
    assert [i.unit for i in rating] == ["Pa (difference)", "m³/s", "kg/m³"]
    assert inputs["Outlet port elevation z_out"].value == 22.0
    values = _values(state, "E1")
    result = state.equipment_results["E1"]
    assert values["Loss coefficient c"] == point_c(POINT)
    assert values["Head loss h = EGL_in − EGL_out (solved)"] == result.head_loss
    assert values["Head loss by the law c Q|Q|"] == pytest.approx(result.head_loss, rel=1e-9)
    assert values["Pressure loss ρ g h"] == result.pressure_loss
    terms = (
        values["Pressure loss ρ g h"]
        + values["Elevation term ρ g (z_out − z_in)"]
        + values["Velocity-head term ρ (v_out² − v_in²)/2"]
    )
    assert values["Static pressure drop Δp_static = p_in − p_out"] == pytest.approx(
        terms, rel=1e-12
    )
    assert values["Density ratio ρ/ρ_r"] == 998.0 / POINT["density"]
    assert values["Flow ratio Q/Q_r"] == result.flow_ratio
    assert any("Silverberg & Darby" in c.name for c in trace.correlations)
    assert {d.name for d in trace.data_sources} >= {"Rating", "Loss coefficient c"}
    notes = trace.notes
    assert notes[0].startswith("The rated drop is the dissipative loss of total pressure")
    assert any(n.startswith("The loss scales with density only.") for n in notes)
    assert any(n.startswith("Density ratio ρ/ρ_r = ") and "lighter than" in n for n in notes)
    assert not any("Reverse flow" in n or "Laminar flow" in n for n in notes)


@pytest.mark.parametrize(("h1", "h2"), [(30.0, 2.0), (2.0, 30.0)])
def test_the_trace_gives_each_port_velocity_once_signed_as_the_flow(h1: float, h2: float) -> None:
    """Review: one velocity per port, v = Q/A of the connected pipe's end segment, signed as the
    flow (inlet → outlet), never a second, unsigned value under the same symbol; each port's
    static pressure and the velocity-head term follow from it. Forward and reverse flow, the
    outlet port 2 m up and its pipe one size down."""
    element = equipment("E1", POINT, elevation=20.0, inlet=20.0, outlet=22.0)
    state = solve_project(line(element, h1=h1, h2=h2, d_out=0.0779))
    trace = state.trace.elements["E1"]
    q = state.equipment_results["E1"].flow
    assert (q > 0.0) == (h1 > h2)
    velocities = {v.name: v.value for v in trace.intermediates if v.unit == "m/s"}
    assert set(velocities) == {
        "Inlet pipe velocity v_in = Q/A_in",
        "Outlet pipe velocity v_out = Q/A_out",
    }
    v_in = velocities["Inlet pipe velocity v_in = Q/A_in"]
    v_out = velocities["Outlet pipe velocity v_out = Q/A_out"]
    assert isinstance(v_in, float)
    assert isinstance(v_out, float)
    assert v_in == pytest.approx(q / _area(D), rel=1e-14)
    assert v_out == pytest.approx(q / _area(0.0779), rel=1e-14)
    assert (v_in > 0.0) == (v_out > 0.0) == (q > 0.0)
    values = _values(state, "E1")
    inputs = {i.name: i.value for i in trace.inputs}
    rho_g = inputs["Fluid density ρ"] * inputs["Gravitational acceleration g"]
    two_g = 2.0 * inputs["Gravitational acceleration g"]
    ports = [("in", "inlet", v_in), ("out", "outlet", v_out)]
    for sub, port, v in ports:
        egl, z = f"EGL at the {port} EGL_{sub}", f"{port.capitalize()} port elevation z_{sub}"
        p = f"{port.capitalize()} static pressure p_{sub}"
        assert values[p] == state.node_results[f"E1:{port}"].pressure
        assert values[p] == pytest.approx(rho_g * (values[egl] - inputs[z] - v * v / two_g))
    rho = inputs["Fluid density ρ"]
    assert values["Velocity-head term ρ (v_out² − v_in²)/2"] == pytest.approx(
        0.5 * rho * (v_out**2 - v_in**2), rel=1e-12
    )


def test_the_trace_of_a_cv_gives_its_rated_point_on_water() -> None:
    state = solve_project(line(equipment("E1", CV)))
    trace = state.trace.elements["E1"]
    [entered] = [i for i in trace.inputs if i.name.startswith("Flow coefficient")]
    assert (entered.name, entered.value, entered.unit, entered.source) == (
        "Flow coefficient Cv (as entered)",
        90.0,
        "US gpm/psi^0.5",
        "user",
    )
    values = _values(state, "E1")
    assert values["Rated point: pressure drop ΔP₁ (1 psi)"] == psi
    assert values["Rated point: flow Q₁ (Cv US gpm)"] == pytest.approx(
        90.0 * gallon / minute, rel=1e-15
    )
    rho_w = values["Water density of the definition ρ_w = ΔP₁/(g c Q₁²)"]
    assert rho_w == pytest.approx(FLUIDS_WATER, rel=1e-9)
    assert values["Density ratio ρ/ρ_w"] == 998.0 / rho_w
    assert "Flow ratio Q/Q_r" not in values
    assert any(d.citation == COEFFICIENT_SOURCE for d in trace.data_sources)
    assert any(c.name == "fluids.fittings.Cv_to_K(Cv, D)" for c in trace.correlations)
    assert any(n.startswith("A Cv is a rated point on water by definition") for n in trace.notes)


def test_a_solve_that_did_not_converge_has_no_equipment_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A check valve in series whose status flips at every outer iteration (the flags audit's
    stand-in for oscillation): not converged, so the element has no result and says why."""

    def flip(old: Status, dh: float, q: float, h_c: float) -> Status:
        return Status.CLOSED if old is Status.OPEN else Status.OPEN

    monkeypatch.setattr(status, "check_valve_status", flip)
    check = {**gate("V", {"kind": "K", "value": 0.5}), "valveType": "check"}
    comps = [reservoir("R1", level=20.0), check, equipment("E1", POINT), reservoir("R2", level=1.0)]
    conns = [
        connection("L1", ("R1", "port_1"), ("V", "inlet")),
        connection("L2", ("V", "outlet"), ("E1", "inlet")),
        connection("L3", ("E1", "outlet"), ("R2", "port_1")),
    ]
    state = solve_project(make_project(comps, conns))
    assert not state.converged
    assert state.equipment_results == {}
    notes = state.trace.elements["E1"].notes
    assert any(n.startswith("The solve did not converge") for n in notes)


# --------------------------------------------------------------------------- methods


TITLES_WITHOUT_EQUIPMENT = [
    "Network solution",
    "Pipe friction",
    "Minor losses",
    "Branches",
    "Pumps",
    "Valves",
    "Fluid properties",
    "Atmosphere and NPSH",
    "Conventions",
]
"""The section titles of method 1.2.0, unchanged for projects without equipment."""
LAST_ASSUMPTION_WITHOUT_EQUIPMENT = (
    "Fittings and valves without a user K use the cited correlation for the type at the "
    "connected pipe's inner diameter."
)


def test_the_methods_summary_has_an_equipment_section_only_with_equipment() -> None:
    plain = solve_project(line(gate("V1", {"kind": "K", "value": 1.0}))).trace.methods
    assert [s.title for s in plain.sections] == TITLES_WITHOUT_EQUIPMENT
    assert len(plain.assumptions) == 8
    assert plain.assumptions[-1] == LAST_ASSUMPTION_WITHOUT_EQUIPMENT
    assert EQUIPMENT_ASSUMPTION not in plain.assumptions
    point = solve_project(line(equipment("E1", POINT))).trace.methods
    titles = [s.title for s in point.sections]
    assert titles == [*TITLES_WITHOUT_EQUIPMENT[:6], "Equipment", *TITLES_WITHOUT_EQUIPMENT[6:]]
    section = point.sections[6]
    assert section.references == [ISA_75, DARBY]
    assert not any("Cv_to_K" in item for item in section.items)
    text = " ".join(section.items)
    # h is a head (m), ρ g h the pressure (review: the item called h a loss of total pressure).
    assert "the loss of total pressure from its inlet" not in text
    for phrase in (
        "the loss of total head from its inlet to its outlet is h = EGL_in − EGL_out = c Q|Q| "
        "(a loss of total pressure ρ g h)",
        "c = ΔP_r/(ρ_r g Q_r²)",
        "without the static head between them",
        "cancels out of the head loss",
        "Reverse flow",
        "Laminar flow (Re < 2000)",
        "1e-06 x the slopes of the pipes",
        "Viscosity is not corrected",
    ):
        assert phrase in text, phrase
    assert point.assumptions == [*plain.assumptions, EQUIPMENT_ASSUMPTION]
    cv = solve_project(line(equipment("E1", KV))).trace.methods
    [item] = [i for i in cv.sections[6].items if "Cv_to_K / Kv_to_K" in i]
    assert item.startswith("A Cv or Kv rating is a rated point on water by definition")


def test_the_equipment_section_and_assumption_are_the_only_additions() -> None:
    """The summary of a project with equipment, with its equipment left out of the built
    network, is the summary without the Equipment section and assumption: every other section
    is as for a project without equipment."""
    project = line(equipment("E1", CV))
    built = _built(project)
    full = methods_summary(built, "test atmosphere")
    built.equipment = {}
    plain = methods_summary(built, "test atmosphere")
    assert plain.sections == [s for s in full.sections if s.title != "Equipment"]
    assert plain.assumptions == full.assumptions[:-1]
    assert full.assumptions[-1] == EQUIPMENT_ASSUMPTION


# --------------------------------------------------------------------------- API


def test_the_api_solves_equipment_and_reports_a_rating_it_cannot_represent() -> None:
    """SDD §5: equipmentResults in camelCase, always present (empty without equipment); the
    rating issue is 422 TOPOLOGY_ERROR naming the element."""
    client = TestClient(app)
    response = client.post("/api/v1/solve", json={"project": line_dict(equipment("E1", POINT))})
    assert response.status_code == 200, response.text
    state = response.json()["solvedState"]
    assert set(state["equipmentResults"]["E1"]) == {
        "flow",
        "flowRatio",
        "headLoss",
        "pressureLoss",
        "pressureDrop",
        "rating",
    }
    assert state["equipmentResults"]["E1"]["rating"] == POINT
    assert state["methodVersion"] == "1.3.0"
    plain = client.post(
        "/api/v1/solve", json={"project": line_dict(gate("V1", {"kind": "K", "value": 1.0}))}
    )
    assert plain.json()["solvedState"]["equipmentResults"] == {}
    bad = line_dict(equipment("E1", {"kind": "Kv", "value": 1.0e-160}))
    response = client.post("/api/v1/solve", json={"project": bad})
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "TOPOLOGY_ERROR"
    assert [(i["code"], i["componentIds"]) for i in body["issues"]] == [
        ("EQUIPMENT_RATING_OUT_OF_RANGE", ["E1"])
    ]
