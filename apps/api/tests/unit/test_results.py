"""Results mapping (design §6): node pressures from EGL and velocity, boundaries, flags."""

import math
import re

import pytest
from CoolProp.CoolProp import PropsSI
from fluids.atmosphere import ATMOSPHERE_1976
from fluids.constants import g
from fluids.fittings import contraction_sharp, diffuser_sharp, entrance_sharp, exit_normal
from fluids.friction import Colebrook
from scipy.optimize import brentq

from opensolve_pipe.models.results import SolvedState
from opensolve_pipe.services.fluids import FluidError, fluid_properties
from opensolve_pipe.services.solver import METHOD_VERSION, solve_project
from opensolve_pipe.services.solver.builder import build_network
from opensolve_pipe.services.solver.results import build_solved_state
from opensolve_pipe.services.solver.status import run_outer_loop

from .helpers import (
    connection,
    custom_fluid,
    custom_pipe,
    make_project,
    plug,
    reference_node,
    reservoir,
    tee,
    two_reservoirs,
)

RHO, MU = 998.0, 1.0e-3
NU = MU / RHO


def area(d: float) -> float:
    return math.pi * d * d / 4


def reducer_project(**kwargs: object) -> SolvedState:
    """R1 -> P1 [0.1 m, reducer, 0.06 m] -> T1 -> P2 [0.06 m, reducer, 0.1 m] -> R2."""
    comps = [
        reservoir("R1", elevation=2.0, level=18.0, surface_pressure=5.0e4),
        tee("T1", elevation=1.0),
        reservoir("R2", level=4.0),
        plug("X1", elevation=1.0),
    ]
    conns = [
        connection(
            "P1",
            ("R1", "port_1"),
            ("T1", "run_inlet"),
            pipes=[custom_pipe(30.0, 0.1, 4.5e-5), custom_pipe(20.0, 0.06, 4.5e-5)],
            fittings=[{"type": "entrance_sharp"}, {"type": "reducer_sudden"}],
        ),
        connection(
            "P2",
            ("T1", "run_outlet"),
            ("R2", "port_1"),
            pipes=[custom_pipe(15.0, 0.06, 4.5e-5), custom_pipe(40.0, 0.1, 4.5e-5)],
            fittings=[{"type": "reducer_sudden"}, {"type": "exit", "pipeIndex": 1}],
        ),
        connection("P3", ("T1", "branch"), ("X1", "port_1"), length=2.0, diameter=0.05),
    ]
    return solve_project(make_project(comps, conns, fluid=custom_fluid(RHO, MU), **kwargs))


def test_node_pressure_from_egl_and_end_segment_velocity() -> None:
    result = reducer_project()
    assert result.converged
    q = result.link_results["P1"].flow
    assert q > 0
    p_atm = result.atmospheric_pressure
    for key in ("T1:run_inlet", "T1:run_outlet"):
        node = result.node_results[key]
        v = q / area(0.06)  # P1's last segment and P2's first segment are 0.06 m
        assert node.velocity == pytest.approx(v, rel=1e-12)
        assert node.hgl == pytest.approx(node.egl - v * v / (2 * g), rel=1e-12)
        assert node.pressure == pytest.approx(RHO * g * (node.hgl - node.elevation), rel=1e-12)
        assert node.dynamic_pressure == pytest.approx(0.5 * RHO * v * v, rel=1e-12)
        assert node.total_pressure == pytest.approx(RHO * g * (node.egl - 1.0), rel=1e-12)
        assert node.absolute_pressure == pytest.approx(node.pressure + p_atm, rel=1e-12)


def friction_loss(q: float, length: float, d: float, eps: float = 4.5e-5) -> float:
    """Darcy–Weisbach with fluids.friction.Colebrook, turbulent flow only (asserted)."""
    re_ = 4 * q / (math.pi * d * NU)
    assert re_ >= 4000.0
    return Colebrook(re_, eps / d) * length / d * (q / area(d)) ** 2 / (2 * g)


def reducer_project_p1_loss(q: float) -> float:
    """EGL loss along P1: friction in both segments, sharp entrance on the 0.1 m pipe, sudden
    contraction (Crane) on the 0.06 m pipe it flows into (fluids docstrings)."""
    return (
        friction_loss(q, 30.0, 0.1)
        + friction_loss(q, 20.0, 0.06)
        + entrance_sharp(method="Crane") * (q / area(0.1)) ** 2 / (2 * g)
        + contraction_sharp(0.1, 0.06, method="Crane") * (q / area(0.06)) ** 2 / (2 * g)
    )


def reducer_project_p2_loss(q: float) -> float:
    """EGL loss along P2: friction in both segments, sudden expansion (diffuser_sharp) on the
    0.06 m pipe it flows out of, exit (exit_normal) on the 0.1 m pipe."""
    return (
        friction_loss(q, 15.0, 0.06)
        + friction_loss(q, 40.0, 0.1)
        + diffuser_sharp(0.06, 0.1) * (q / area(0.06)) ** 2 / (2 * g)
        + exit_normal() * (q / area(0.1)) ** 2 / (2 * g)
    )


H_R1 = 2.0 + 18.0 + 5.0e4 / (RHO * g)  # z + level + p_surface/(ρg)
H_R2 = 0.0 + 4.0


def reducer_project_flow() -> float:
    """Series energy equation H_R1 − H_R2 = h_P1(Q) + h_P2(Q) (P3 is a dead end), by brentq,
    bracketed from Re = 4000 in the 0.1 m pipe (the lowest Re of all segments) upwards."""
    q_turbulent = 4000.0 * NU * math.pi * 0.1 / 4  # Re = 4Q/(π D ν)
    root: float = brentq(
        lambda q: reducer_project_p1_loss(q) + reducer_project_p2_loss(q) - (H_R1 - H_R2),
        q_turbulent,
        1.0,
        xtol=1e-16,
        rtol=1e-15,
    )
    return root


def test_reducer_project_flow_matches_an_independent_energy_balance() -> None:
    result = reducer_project()
    q = reducer_project_flow()
    assert result.link_results["P1"].flow == pytest.approx(q, rel=1e-9)
    assert result.link_results["P2"].flow == pytest.approx(q, rel=1e-9)
    assert result.link_results["P3"].flow == 0.0


def test_tee_pressure_matches_an_independent_energy_balance() -> None:
    """EGL at T1 = H_R1 − (friction + entrance + contraction) along P1, at the flow derived
    above; static pressure from that EGL and the 0.06 m pipe's velocity head."""
    result = reducer_project()
    q = reducer_project_flow()
    node = result.node_results["T1:run_inlet"]
    egl = H_R1 - reducer_project_p1_loss(q)
    tol = 1e-7  # m, the solver's energy-residual tolerance
    assert node.egl == pytest.approx(egl, abs=tol)
    v = q / area(0.06)
    expected_p = RHO * g * (egl - v * v / (2 * g) - 1.0)
    assert node.pressure == pytest.approx(expected_p, abs=RHO * g * tol)
    # The outlet port sees the same EGL (ideal tee) and P2's first (0.06 m) segment velocity.
    outlet = result.node_results["T1:run_outlet"]
    assert outlet.egl == pytest.approx(H_R2 + reducer_project_p2_loss(q), abs=tol)
    # The expansion on P2 is diffuser_sharp on the small, upstream pipe.
    fitting = result.link_results["P2"].fittings[0]
    assert fitting.k == diffuser_sharp(0.06, 0.1)
    assert fitting.reference_diameter == 0.06


def test_boundary_ports_report_the_quiescent_boundary() -> None:
    result = reducer_project()
    node = result.node_results["R1:port_1"]
    assert node.velocity == 0.0
    assert node.hgl == node.egl == pytest.approx(2.0 + 18.0 + 5.0e4 / (RHO * g), rel=1e-15)
    assert node.pressure == pytest.approx(RHO * g * 18.0 + 5.0e4, rel=1e-12)
    assert node.dynamic_pressure == 0.0
    boundary = result.boundary_results["R1"]
    assert boundary.type == "reservoir"
    assert boundary.egl == node.egl
    assert boundary.outflow == pytest.approx(result.link_results["P1"].flow, rel=1e-15)
    assert boundary.port_outflows == {"port_1": boundary.outflow}
    assert result.boundary_results["X1"].type == "plug"


def test_reference_node_holds_its_pressure() -> None:
    comps = [reference_node("S", pressure=3.0e5, elevation=4.0), reservoir("R2", level=2.0)]
    conns = [connection("P1", ("S", "port_1"), ("R2", "port_1"))]
    result = solve_project(make_project(comps, conns, fluid=custom_fluid(RHO, MU)))
    node = result.node_results["S:port_1"]
    assert node.egl == pytest.approx(4.0 + 3.0e5 / (RHO * g), rel=1e-15)
    assert node.pressure == pytest.approx(3.0e5, rel=1e-12)
    assert result.boundary_results["S"].type == "reference_node"


def test_link_result_breakdown_adds_up() -> None:
    result = reducer_project()
    link = result.link_results["P1"]
    assert [s.inner_diameter for s in link.segments] == [0.1, 0.06]
    assert link.velocity == link.segments[0].velocity
    assert link.reynolds_number == link.segments[0].reynolds_number
    assert link.friction_head_loss + link.fittings_head_loss == pytest.approx(
        link.head_loss, abs=1e-7
    )
    assert link.fittings[0].k == entrance_sharp(method="Crane")
    assert link.fittings[1].k == contraction_sharp(0.1, 0.06, method="Crane")
    assert all(f.source for f in link.fittings)


@pytest.mark.parametrize(("site", "override"), [(0.0, None), (1500.0, None), (1500.0, 95000.0)])
def test_atmospheric_pressure_from_site_elevation_or_override(
    site: float, override: float | None
) -> None:
    result = reducer_project(site_elevation=site, atmospheric_pressure=override)
    expected = override if override is not None else ATMOSPHERE_1976(site).P
    assert result.atmospheric_pressure == expected
    node = result.node_results["T1:branch"]
    assert node.absolute_pressure == pytest.approx(node.pressure + expected, rel=1e-12)
    conventions = next(s for s in result.trace.methods.sections if s.title == "Conventions")
    source = "user override" if override is not None else "ATMOSPHERE_1976"
    assert any(source in item for item in conventions.items)


def test_port_above_liquid_level_is_flagged() -> None:
    comps = [reservoir("R1", level=3.0, port_elevation=5.0), reservoir("R2", level=1.0)]
    conns = [connection("P1", ("R1", "port_1"), ("R2", "port_1"))]
    result = solve_project(make_project(comps, conns))
    [flag] = [f for f in result.flags if f.code == "PORT_ABOVE_LIQUID_LEVEL"]
    assert (flag.severity, flag.component_id, flag.port_id) == ("invalid", "R1", "port_1")


def siphon(vapor_pressure: float | None) -> SolvedState:
    """A dead-end branch 20 m above the reservoir surface: absolute pressure < 0."""
    comps = [
        reservoir("R1", level=1.0),
        tee("T1"),
        reservoir("R2", level=0.5),
        plug("TOP", elevation=20.0),
    ]
    conns = [
        connection("P1", ("R1", "port_1"), ("T1", "run_inlet")),
        connection("P2", ("T1", "run_outlet"), ("R2", "port_1")),
        connection("P3", ("T1", "branch"), ("TOP", "port_1")),
    ]
    fluid = custom_fluid(RHO, MU, vapor_pressure=vapor_pressure)
    return solve_project(make_project(comps, conns, fluid=fluid))


def test_below_vapor_pressure_is_flagged_when_vapor_pressure_is_known() -> None:
    result = siphon(2339.0)
    flagged = {
        f"{f.component_id}:{f.port_id}" for f in result.flags if f.code == "BELOW_VAPOR_PRESSURE"
    }
    assert "TOP:port_1" in flagged
    assert all(f.severity == "invalid" for f in result.flags if f.code == "BELOW_VAPOR_PRESSURE")
    assert "R1:port_1" not in flagged
    assert not any(f.code == "NO_VAPOR_PRESSURE" for f in result.flags)


def test_negative_absolute_pressure_is_flagged_without_a_vapor_pressure() -> None:
    """No vapor pressure given: an absolute pressure at or below zero is still impossible for a
    liquid (its vapor pressure is positive), so it is flagged with 0 Pa as the bound."""
    result = siphon(None)
    top = result.node_results["TOP:port_1"]
    assert top.absolute_pressure < 0
    [flag] = [
        f
        for f in result.flags
        if f.code == "BELOW_VAPOR_PRESSURE" and (f.component_id, f.port_id) == ("TOP", "port_1")
    ]
    assert flag.severity == "invalid"
    assert flag.details == {"absolutePressure": top.absolute_pressure, "vaporPressure": "not given"}
    flagged = {
        (f.component_id, f.port_id) for f in result.flags if f.code == "BELOW_VAPOR_PRESSURE"
    }
    unflagged = {
        (n.component_id, n.port_id) for n in result.node_results.values() if n.absolute_pressure > 0
    }
    assert not flagged & unflagged
    [info] = [f for f in result.flags if f.code == "NO_VAPOR_PRESSURE"]
    assert info.severity == "info"


def test_siphon_crest_without_vapor_pressure_is_flagged() -> None:
    """Review case: R1 (z 0, level 1 m) -> 50 m of 50 mm pipe -> ideal tee at 15 m (plugged
    branch) -> 50 m of pipe -> R2 at z = −20 m, custom fluid without a vapor pressure."""
    comps = [
        reservoir("R1", level=1.0),
        tee("T1", elevation=15.0),
        plug("PL", elevation=15.0),
        reservoir("R2", elevation=-20.0, level=1.0),
    ]
    conns = [
        connection("P1", ("R1", "port_1"), ("T1", "run_inlet"), length=50, diameter=0.05),
        connection("P2", ("T1", "run_outlet"), ("R2", "port_1"), length=50, diameter=0.05),
        connection("P3", ("T1", "branch"), ("PL", "port_1"), length=1, diameter=0.05),
    ]
    result = solve_project(make_project(comps, conns, fluid=custom_fluid(RHO, MU)))
    assert result.node_results["T1:run_inlet"].absolute_pressure < 0
    flagged = {
        f"{f.component_id}:{f.port_id}" for f in result.flags if f.code == "BELOW_VAPOR_PRESSURE"
    }
    assert {"T1:run_inlet", "T1:run_outlet", "T1:branch", "PL:port_1"} <= flagged


def test_reference_node_below_absolute_zero_is_flagged() -> None:
    """A gauge pressure below −p_atm (allowed down to −1e5 Pa) at a high site."""
    site = 2000.0
    p_gauge = -9.0e4
    assert p_gauge + ATMOSPHERE_1976(site).P < 0  # premise of the case
    comps = [reservoir("R1", level=2.0), reference_node("S", pressure=p_gauge)]
    conns = [connection("P1", ("R1", "port_1"), ("S", "port_1"))]
    result = solve_project(make_project(comps, conns, site_elevation=site))
    assert any(
        f.code == "BELOW_VAPOR_PRESSURE" and (f.component_id, f.port_id) == ("S", "port_1")
        for f in result.flags
    )


@pytest.mark.parametrize(("temperature", "site"), [(368.15, 2000.0), (373.15, 0.0)])
def test_boiling_open_reservoir_is_flagged(temperature: float, site: float) -> None:
    """Hot water in an open tank whose surface (at p_atm) is below the vapor pressure."""
    p_vap = PropsSI("P", "T", temperature, "Q", 0, "Water")  # CoolProp 'Water', IAPWS-95
    p_atm = ATMOSPHERE_1976(site).P
    assert p_atm < p_vap  # premise: the open surface boils
    comps, conns = two_reservoirs(h1=3.0, h2=1.0, length=20.0, diameter=0.05)
    water = {"kind": "builtin", "fluidId": "water", "temperature": temperature}
    result = solve_project(make_project(comps, conns, fluid=water, site_elevation=site))
    boiling = [f for f in result.flags if f.code == "BELOW_VAPOR_PRESSURE" and f.port_id is None]
    assert {f.component_id for f in boiling} == {"R1", "R2"}
    for flag in boiling:
        assert flag.severity == "invalid"
        assert flag.details["surfaceAbsolutePressure"] == pytest.approx(p_atm, rel=1e-12)
        assert flag.details["vaporPressure"] == pytest.approx(p_vap, rel=1e-12)


def test_pressurized_hot_reservoir_is_not_flagged() -> None:
    temperature, site = 368.15, 2000.0
    p_vap = PropsSI("P", "T", temperature, "Q", 0, "Water")
    surface = 1.0e4  # Pa gauge, enough to lift the surface above the vapor pressure
    assert ATMOSPHERE_1976(site).P + surface > p_vap  # premise
    comps = [
        reservoir("R1", level=3.0, surface_pressure=surface),
        reservoir("R2", level=1.0, surface_pressure=surface),
    ]
    conns = [connection("P1", ("R1", "port_1"), ("R2", "port_1"), length=20.0, diameter=0.05)]
    water = {"kind": "builtin", "fluidId": "water", "temperature": temperature}
    result = solve_project(make_project(comps, conns, fluid=water, site_elevation=site))
    assert not any(f.code == "BELOW_VAPOR_PRESSURE" for f in result.flags)


def test_reservoir_surface_below_absolute_zero_is_flagged_without_a_vapor_pressure() -> None:
    site = 3000.0
    surface = -9.0e4
    assert ATMOSPHERE_1976(site).P + surface < 0  # premise
    comps = [reservoir("R1", level=3.0, surface_pressure=surface), reservoir("R2", level=1.0)]
    conns = [connection("P1", ("R2", "port_1"), ("R1", "port_1"))]
    result = solve_project(make_project(comps, conns, site_elevation=site))
    assert any(
        f.code == "BELOW_VAPOR_PRESSURE" and f.component_id == "R1" and f.port_id is None
        for f in result.flags
    )


def test_transitional_flow_is_flagged() -> None:
    # Re ≈ 3000 in a 20 mm pipe: v = Re ν / D.
    d = 0.02
    q = 3000 * NU / d * area(d)
    comps, conns = two_reservoirs(h1=1.0, h2=1.0, length=10.0, diameter=d)
    # Set the head difference that drives roughly that flow (a test input, not an expectation).
    dh = 0.04 * 10.0 / d * (q / area(d)) ** 2 / (2 * g)
    comps[0]["liquidLevel"] = 1.0 + dh
    result = solve_project(make_project(comps, conns, fluid=custom_fluid(RHO, MU)))
    link = result.link_results["P1"]
    assert link.flow_regime == "transitional"
    [flag] = [f for f in result.flags if f.code == "TRANSITIONAL_FLOW"]
    assert (flag.severity, flag.connection_id, flag.details["segmentIndex"]) == ("warning", "P1", 0)


def laminar_with_fittings(fittings: list[dict[str, object]], h1: float = 2.0) -> SolvedState:
    comps, conns = two_reservoirs(
        h1=h1, h2=1.0, length=10.0, diameter=0.02, roughness=0.0, fittings=fittings
    )
    return solve_project(make_project(comps, conns, fluid=custom_fluid(900.0, 0.5)))


def test_crane_fitting_in_laminar_flow_is_flagged() -> None:
    result = laminar_with_fittings([{"type": "elbow_90_lr"}, {"type": "custom", "kOverride": 1.0}])
    assert result.link_results["P1"].flow_regime == "laminar"
    flags = [f for f in result.flags if f.code == "CORRELATION_OUT_OF_RANGE"]
    assert [f.details["fittingIndex"] for f in flags] == [0]  # not the user K
    assert flags[0].severity == "warning"


def test_no_laminar_flag_at_zero_flow() -> None:
    result = laminar_with_fittings([{"type": "elbow_90_lr"}], h1=1.0)
    assert result.link_results["P1"].flow == 0.0
    assert not any(f.code == "CORRELATION_OUT_OF_RANGE" for f in result.flags)


def test_bend_outside_the_crane_table_is_flagged() -> None:
    comps, conns = two_reservoirs(fittings=[{"type": "bend", "angle": 90, "radiusRatio": 30}])
    result = solve_project(make_project(comps, conns))
    [flag] = [f for f in result.flags if f.code == "CORRELATION_OUT_OF_RANGE"]
    assert flag.connection_id == "P1"
    assert "outside the Crane r/D table" in flag.message


def test_metadata_trace_and_methods() -> None:
    result = reducer_project()
    assert result.method_version == METHOD_VERSION
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", result.timestamp)
    assert result.fluid.density == RHO
    assert result.trace.elements == {}
    methods = result.trace.methods
    titles = [s.title for s in methods.sections]
    assert titles[:3] == ["Network solution", "Pipe friction", "Minor losses"]
    assert {"fluids", "CoolProp", "numpy", "scipy", "opensolve-pipe"} <= set(methods.libraries)
    assert result.pump_results == result.valve_results == {}
    assert set(result.node_results) == {
        "R1:port_1",
        "T1:run_inlet",
        "T1:run_outlet",
        "T1:branch",
        "R2:port_1",
        "X1:port_1",
    }


def test_builtin_water_project() -> None:
    comps, conns = two_reservoirs(h1=12.0, h2=10.0)
    fluid = {"kind": "builtin", "fluidId": "water", "temperature": 293.15}
    result = solve_project(make_project(comps, conns, fluid=fluid))
    assert result.converged
    assert result.fluid.name == "Water"
    with pytest.raises(FluidError):
        solve_project(make_project(comps, conns, fluid={**fluid, "temperature": 260.0}))


def test_m3_elements_raise_not_implemented() -> None:
    pump = {
        "type": "pump",
        "id": "PU",
        "name": "PU",
        "elevation": 0,
        "curveId": "C1",
        "ports": [{"id": "suction", "nominalSize": 0.1}, {"id": "discharge", "nominalSize": 0.1}],
    }
    curve = {
        "id": "C1",
        "name": "c",
        "points": [{"flow": 0, "head": 30}, {"flow": 0.01, "head": 28}, {"flow": 0.02, "head": 20}],
    }
    comps = [reservoir("R1"), pump, reservoir("R2")]
    conns = [
        connection("L1", ("R1", "port_1"), ("PU", "suction")),
        connection("L2", ("PU", "discharge"), ("R2", "port_1")),
    ]
    with pytest.raises(NotImplementedError, match=r"pump 'PU'.*M3"):
        solve_project(make_project(comps, conns, pump_library=[curve]))

    valve = {
        "type": "valve",
        "valveType": "gate",
        "id": "V",
        "name": "V",
        "elevation": 0,
        "ports": [{"id": "inlet", "nominalSize": 0.1}, {"id": "outlet", "nominalSize": 0.1}],
    }
    conns = [
        connection("L1", ("R1", "port_1"), ("V", "inlet")),
        connection("L2", ("V", "outlet"), ("R2", "port_1")),
    ]
    with pytest.raises(NotImplementedError, match="gate valve 'V'"):
        solve_project(make_project([reservoir("R1"), valve, reservoir("R2")], conns))

    comps = [reservoir("R1"), tee("T", loss_model="crane"), reservoir("R2"), plug("X")]
    conns = [
        connection("L1", ("R1", "port_1"), ("T", "run_inlet")),
        connection("L2", ("T", "run_outlet"), ("R2", "port_1")),
        connection("L3", ("T", "branch"), ("X", "port_1")),
    ]
    with pytest.raises(NotImplementedError, match="lossModel 'crane'"):
        solve_project(make_project(comps, conns))


def friction_range_flags(result: SolvedState) -> list[dict[str, float | str]]:
    return [
        f.details
        for f in result.flags
        if f.code == "CORRELATION_OUT_OF_RANGE" and "segmentIndex" in f.details
    ]


@pytest.mark.parametrize("method", ["colebrook", "swamee_jain"])
def test_extreme_relative_roughness_is_flagged(method: str) -> None:
    """Review case: D = 5 mm, L = 1 m, 100 m of head, ε = 2.5 mm (ε/D = 0.5): far beyond the
    documented ranges (fluids.friction.fmethods: Swamee_Jain_1976 and Haaland, ε/D ≤ 0.05)."""
    comps, conns = two_reservoirs(h1=110.0, h2=10.0, length=1.0, diameter=0.005, roughness=0.0025)
    result = solve_project(make_project(comps, conns, method=method))
    assert result.link_results["P1"].flow_regime == "turbulent"
    [details] = friction_range_flags(result)
    assert details["segmentIndex"] == 0
    assert details["relativeRoughness"] == pytest.approx(0.5, rel=1e-12)


def test_swamee_jain_below_its_reynolds_range_is_flagged() -> None:
    """4000 <= Re < 5000 is turbulent (EPANET's threshold) but below Swamee–Jain's documented
    5e3 <= Re (fluids docstring)."""
    d, re_target = 0.02, 4500.0
    q = re_target * NU / d * area(d)
    comps, conns = two_reservoirs(h1=1.0, h2=1.0, length=10.0, diameter=d)
    # Head difference that drives roughly that flow (a test input, not an expectation).
    comps[0]["liquidLevel"] = 1.0 + 0.04 * 10.0 / d * (q / area(d)) ** 2 / (2 * g)
    result = solve_project(
        make_project(comps, conns, fluid=custom_fluid(RHO, MU), method="swamee_jain")
    )
    re_solved = result.link_results["P1"].reynolds_number
    assert 4000.0 <= re_solved < 5000.0
    [details] = friction_range_flags(result)
    assert details["reynoldsNumber"] == pytest.approx(re_solved, rel=1e-12)
    colebrook = solve_project(make_project(comps, conns, fluid=custom_fluid(RHO, MU)))
    assert friction_range_flags(colebrook) == []


def test_ordinary_pipe_has_no_friction_range_flag() -> None:
    assert friction_range_flags(reducer_project()) == []


def test_dead_end_trees_report_exactly_zero_flow() -> None:
    """A tree of pipes off the network with no fixed head (plugged branches) carries no flow
    by continuity alone; solver noise there is reported as zero, real flows are untouched."""
    comps = [
        reservoir("R1", level=20.0),
        tee("T1"),
        reservoir("R2", level=10.0),
        tee("T2", elevation=1.0),
        plug("X1", elevation=2.0),
        plug("X2", elevation=3.0),
    ]
    conns = [
        connection("P1", ("R1", "port_1"), ("T1", "run_inlet"), length=60.0),
        connection("P2", ("T1", "run_outlet"), ("R2", "port_1"), length=40.0),
        connection("P3", ("T1", "branch"), ("T2", "run_inlet"), diameter=2.0, length=0.5),
        connection("P4", ("T2", "run_outlet"), ("X1", "port_1"), diameter=2.0, length=0.5),
        connection("P5", ("T2", "branch"), ("X2", "port_1"), diameter=2.0, length=0.5),
    ]
    project = make_project(comps, conns, fluid=custom_fluid(RHO, MU))
    built = build_network(project, fluid_properties(project.fluid))
    outer = run_outer_loop(built, tolerance=1e-9, max_iterations=100)
    main = outer.gga.flows[built.connections["P1"].link_index]
    # Noise of the size a poorly conditioned linear solve leaves in large-bore dead ends.
    noisy = outer.gga.flows.copy()
    for cid in ("P3", "P4", "P5"):
        noisy[built.connections[cid].link_index] = 1.0e-9 * main
    outer.gga.flows = noisy
    result = build_solved_state(built, outer, 101325.0, "test")
    for cid in ("P3", "P4", "P5"):
        assert result.link_results[cid].flow == 0.0
        assert result.link_results[cid].flow_regime == "none"
    assert result.link_results["P1"].flow == main
    assert result.link_results["P2"].flow == outer.gga.flows[built.connections["P2"].link_index]
    assert result.branch_results["T2"].pattern == "no flow"
