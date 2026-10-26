"""Per-element calculation trace (design §13, GOALS §4.2).

Over every reference-suite project: each component and connection has a trace with inputs and
equations; every intermediate value that restates a result field equals it; intermediate values
computed in the trace obey their own equations (v = Q/A, NPSHa = (EGL_s − z_s) + (p_atm −
p_vap)/(ρg), H = z + h_L + p_s/(ρg)); units are the strings the frontend understands. Plus the
traces of elements without a result (a closed-off section, a solve that did not converge) and
the user / default sources of inputs.
"""

import math
from pathlib import Path
from typing import Any

import pytest
from fluids.constants import g

from opensolve_pipe.models.components import (
    CheckValve,
    ControlValve,
    IdealReferenceNode,
    IsolationValve,
    Pump,
    Reservoir,
    TeeBranch,
    WyeBranch,
)
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import ElementTrace, SolvedState
from opensolve_pipe.services.solver import solve_project
from opensolve_pipe.services.solver.trace import BOUNDARY_LOSS_NOTE
from tests.reference.case_format import case_files, read_case

from .helpers import connection, custom_pipe, make_project, reference_node, reservoir, tee

CASES = case_files()

PRESSURE_UNITS = {"Pa(g)", "Pa(a)", "Pa (difference)"}
"""Every pressure in a trace states its reference (apps/web/src/lib/utils/trace.ts)."""
CONVERTED_UNITS = {"m", "m³/s", "m/s", "kg/m³", "Pa·s", "W"} | PRESSURE_UNITS
SHOWN_AS_IS = {"", "m²", "m²/s", "m/s²", "°", "US gpm/psi^0.5", "m³/h/bar^0.5", "s²/m⁵"}
"""Units the web shows as reported (utils/trace.ts: anything it does not convert); s²/m⁵ is an
equipment element's loss coefficient c (proposal equipment-pressure-drop.md §4.1)."""


def _solve(path: Path) -> tuple[Project, SolvedState]:
    project = Project.model_validate(read_case(path)["project"])
    return project, solve_project(project)


def _values(trace: ElementTrace) -> dict[str, float]:
    values = {v.name: v.value for v in trace.intermediates}
    assert len(values) == len(trace.intermediates), f"{trace.element_id}: duplicate names"
    return values


def _inputs(trace: ElementTrace) -> dict[str, Any]:
    return {i.name: i.value for i in trace.inputs}


@pytest.fixture(scope="module", params=CASES, ids=lambda p: p.stem)
def solved(request: pytest.FixtureRequest) -> tuple[Project, SolvedState]:
    return _solve(request.param)


def test_every_element_has_a_trace_with_inputs_and_equations(
    solved: tuple[Project, SolvedState],
) -> None:
    project, state = solved
    ids = {c.id for c in project.components} | {c.id for c in project.connections}
    assert set(state.trace.elements) == ids
    for eid, trace in state.trace.elements.items():
        assert trace.element_id == eid
        assert trace.inputs, eid
        assert trace.equations, eid
        assert all(r.name and r.citation for r in trace.correlations + trace.data_sources), eid


def test_trace_units_and_values_are_well_formed(solved: tuple[Project, SolvedState]) -> None:
    _, state = solved
    for trace in state.trace.elements.values():
        for value in trace.intermediates:
            assert math.isfinite(value.value), (trace.element_id, value.name)
            assert value.unit in CONVERTED_UNITS | SHOWN_AS_IS, (trace.element_id, value.unit)
        for item in trace.inputs:
            assert item.unit in CONVERTED_UNITS | SHOWN_AS_IS | {"K"}, (trace.element_id, item)
            assert item.unit != "Pa"
            if isinstance(item.value, float):
                assert math.isfinite(item.value)
    # The state serializes as the API sends it.
    assert state.model_dump_json()


def test_connection_intermediates_match_the_link_results(
    solved: tuple[Project, SolvedState],
) -> None:
    project, state = solved
    for conn in project.connections:
        link = state.link_results[conn.id]
        values = _values(state.trace.elements[conn.id])
        assert values["Flow Q"] == link.flow
        assert values["Head loss Δh = EGL_from − EGL_to"] == link.head_loss
        assert values["Friction head loss Σh_f"] == link.friction_head_loss
        assert values["Fittings head loss Σh_j"] == link.fittings_head_loss
        for seg in link.segments:
            i = seg.index
            assert values[f"Pipe {i + 1} velocity v"] == seg.velocity
            assert values[f"Pipe {i + 1} Reynolds number Re"] == seg.reynolds_number
            assert values[f"Pipe {i + 1} friction factor f"] == seg.friction_factor
            assert values[f"Pipe {i + 1} friction head loss h_f"] == seg.head_loss
            assert values[f"Pipe {i + 1} relative roughness ε/D"] == pytest.approx(
                seg.roughness / seg.inner_diameter, rel=1e-15
            )
            area = values[f"Pipe {i + 1} area A"]
            assert area == pytest.approx(math.pi * seg.inner_diameter**2 / 4, rel=1e-15)
            assert seg.velocity == pytest.approx(link.flow / area, rel=1e-12, abs=1e-300)
        for fit in link.fittings:
            assert values[f"Fitting {fit.index + 1} K"] == fit.k
            assert values[f"Fitting {fit.index + 1} reference diameter"] == fit.reference_diameter
            assert values[f"Fitting {fit.index + 1} head loss h_j"] == fit.head_loss
        a = f"{conn.from_component_id}:{conn.from_port_id}"
        b = f"{conn.to_component_id}:{conn.to_port_id}"
        if a in state.node_results:
            assert values["EGL at the from port"] == state.node_results[a].egl
        if b in state.node_results:
            assert values["EGL at the to port"] == state.node_results[b].egl


def test_component_intermediates_match_their_results(
    solved: tuple[Project, SolvedState],
) -> None:
    project, state = solved
    rho_g = state.fluid.density * g
    for comp in project.components:
        trace = state.trace.elements[comp.id]
        values = _values(trace)
        if isinstance(comp, Reservoir | IdealReferenceNode):
            boundary = state.boundary_results[comp.id]
            assert values["Boundary head H (EGL)"] == boundary.egl
            assert values["Net outflow Q_out"] == boundary.outflow
            if isinstance(comp, Reservoir):
                # H = z + h_L + p_s/(ρ g), from the reservoir's own inputs.
                assert boundary.egl == pytest.approx(
                    comp.elevation + comp.liquid_level + comp.surface_pressure / rho_g,
                    rel=1e-14,
                    abs=1e-12,
                )
        elif isinstance(comp, Pump) and comp.id in state.pump_results:
            pump = state.pump_results[comp.id]
            assert values["Operating flow Q"] == pump.operating_flow
            assert values["Pump head H (EGL rise)"] == pump.operating_head
            assert values["Suction absolute pressure p_s,abs"] == pump.suction_absolute_pressure
            for name, field in (
                ("NPSH available NPSHa", pump.npsh_available),
                ("NPSH required NPSHr", pump.npsh_required),
                ("NPSH margin", pump.npsh_margin),
                ("Efficiency η", pump.efficiency),
                ("Shaft power P_shaft", pump.shaft_power),
            ):
                assert values.get(name) == field, name
            assert values["Hydraulic power P_hyd"] == pump.hydraulic_power
            if pump.npsh_available is not None:
                # The NPSHa terms listed add up to NPSHa (design §8).
                terms = (
                    values["Head above the suction port EGL_s − z_s"]
                    + values["Atmospheric minus vapor pressure head (p_atm − p_vap)/(ρg)"]
                )
                assert terms == pytest.approx(pump.npsh_available, rel=1e-12, abs=1e-12)
                assert values["Atmospheric minus vapor pressure head (p_atm − p_vap)/(ρg)"] == (
                    pytest.approx(
                        (state.atmospheric_pressure - (state.fluid.vapor_pressure or 0.0)) / rho_g,
                        rel=1e-14,
                    )
                )
        elif isinstance(comp, IsolationValve | CheckValve | ControlValve):
            valve = state.valve_results.get(comp.id)
            if valve is None:
                continue
            assert values["Fully open K"] == valve.k_open
            assert values["Flow Q"] == valve.flow
            assert values["Head loss EGL_in − EGL_out"] == valve.head_loss
            assert values["Static pressure drop Δp"] == valve.pressure_drop
            assert values.get("Effective K_eff (throttling)") == valve.k_effective
            assert values.get("Effective Cv_eff (throttling)") == valve.cv_effective
            if (
                isinstance(comp, ControlValve)
                and comp.valve_type == "prv"
                and valve.state == "active"
            ):
                held = state.node_results[f"{comp.id}:outlet"]
                assert held.pressure == pytest.approx(comp.setpoint, rel=1e-9, abs=1e-6)
                assert values["Setpoint head H_set"] == pytest.approx(held.egl, abs=1e-9)
        elif isinstance(comp, TeeBranch | WyeBranch):
            branch = state.branch_results.get(comp.id)
            if branch is None:
                continue
            for port, q in branch.port_flows.items():
                assert values[f"Port {port} flow (into the {comp.branch_type})"] == q
            if branch.combined_port_id is not None:
                c = branch.combined_port_id
                arrow = "→" if branch.pattern.startswith("diverging") else "←"
                assert values["Reference velocity v_c"] == branch.reference_velocity
                for port, k in branch.k_factors.items():
                    assert values[f"K, path {c} {arrow} {port}"] == k
                for port, h in branch.path_head_losses.items():
                    assert values[f"Path head loss, {c} {arrow} {port}"] == h


def test_inputs_restate_the_project(solved: tuple[Project, SolvedState]) -> None:
    project, state = solved
    for conn in project.connections:
        inputs = _inputs(state.trace.elements[conn.id])
        for i, pipe in enumerate(conn.piping.pipes):
            assert inputs[f"Pipe {i + 1} length L"] == pipe.length
            if pipe.inner_diameter is not None:
                assert inputs[f"Pipe {i + 1} inner diameter D"] == pipe.inner_diameter
        for j, fit in enumerate(conn.piping.fittings):
            assert inputs[f"Fitting {j + 1} ({fit.type}) quantity n"] == fit.quantity
    for comp in project.components:
        inputs = _inputs(state.trace.elements[comp.id])
        if isinstance(comp, Pump):
            curve = next(c for c in project.pump_library if c.id == comp.curve_id)
            for i, point in enumerate(curve.points):
                assert inputs[f"Head curve point {i + 1}: flow Q₀"] == point.flow
                assert inputs[f"Head curve point {i + 1}: head H₀"] == point.head
            if comp.control is None:
                assert inputs["Speed ratio s"] == comp.speed
            else:  # speed-controlled (CLAUDE.md D11): speed is the maximum speed
                assert "Speed ratio s" not in inputs
                assert inputs["Maximum speed s_max (field speed)"] == comp.speed
                assert inputs["Minimum speed s_min"] == comp.control.min_speed
                assert inputs["Flow setpoint Q_set"] == comp.control.setpoint
                assert inputs["Control mode"] == comp.control.mode
            assert inputs["Atmospheric pressure p_atm"] == state.atmospheric_pressure
            assert inputs["Vapor pressure p_vap"] == state.fluid.vapor_pressure
        if isinstance(comp, ControlValve) and comp.valve_type != "fcv":
            port = "outlet" if comp.valve_type == "prv" else "inlet"
            assert inputs[f"Setpoint p_set ({port} static pressure)"] == comp.setpoint


def test_pump_trace_states_no_viscosity_correction() -> None:
    _, state = _solve(next(p for p in CASES if p.stem == "pump_single_pipe"))
    trace = state.trace.elements["PU1"]
    assert any("No viscosity correction applied" in n for n in trace.notes)
    names = [c.name for c in trace.correlations]
    assert any("PchipInterpolator" in n for n in names)
    assert any(r.name.startswith("Atmospheric pressure") for r in trace.data_sources)


def test_crane_tee_trace_names_the_correlation_and_the_flow_ratio() -> None:
    _, state = _solve(next(p for p in CASES if p.stem == "tee_crane_diverging"))
    trace = state.trace.elements["T1"]
    values = _values(trace)
    branch = state.branch_results["T1"]
    q_c = abs(branch.port_flows[branch.combined_port_id or ""])
    assert values["Branch flow ratio q = Q_branch/Q_c"] == pytest.approx(
        abs(branch.port_flows["branch"]) / q_c, rel=1e-14
    )
    assert "Diameter ratio β = D_branch/D_run" in values
    assert any("K_branch_diverging_Crane" in c.name for c in trace.correlations)
    assert all("Crane" in c.citation for c in trace.correlations)


def test_control_valve_trace_names_the_status_rule() -> None:
    for name, vid, rule in (
        ("prv_active", "PRV1", "prvstatus"),
        ("psv_open", "PSV1", "psvstatus"),
        ("fcv_closed_reverse", "FCV1", "fcvstatus"),
    ):
        path = next((p for p in CASES if p.stem == name), None)
        assert path is not None, name
        _, state = _solve(path)
        notes = state.trace.elements[vid].notes
        assert any(rule in n and n.startswith("State ") for n in notes), (name, notes)


def test_isolated_elements_have_a_trace_that_says_why() -> None:
    _, state = _solve(next(p for p in CASES if p.stem == "isolation_valves_isolated_section"))
    isolated = [
        cid
        for cid in state.trace.elements
        if cid in ("V1", "V2") and cid not in state.valve_results
    ]
    assert isolated
    for cid in isolated:
        trace = state.trace.elements[cid]
        assert trace.inputs
        assert trace.equations
        assert not trace.intermediates
        assert any("closed off" in n for n in trace.notes), trace.notes


def test_unconverged_solve_still_traces_every_element() -> None:
    """A wye whose combined flow passes through its lateral has no cited correlation: the solve
    is reported as not converged (design §5.4), but every element keeps its inputs, equations
    and sources, with a note instead of values."""
    comps = [
        reservoir("R1", level=10.0),
        reservoir("R2", level=10.0),
        reservoir("R3", level=19.0),
        {
            "type": "branch",
            "branchType": "wye",
            "id": "W",
            "name": "W",
            "elevation": 0.0,
            "angle": 45.0,
            "ports": [{"id": p, "nominalSize": 0.1} for p in ("inlet", "outlet_1", "outlet_2")],
        },
    ]
    conns = [
        connection("L1", ("W", "inlet"), ("R1", "port_1"), length=50.0),
        connection("L2", ("W", "outlet_1"), ("R2", "port_1"), length=50.0),
        connection("L3", ("R3", "port_1"), ("W", "outlet_2"), length=30.0),
    ]
    state = solve_project(make_project(comps, conns))
    assert not state.converged
    assert set(state.trace.elements) == {"R1", "R2", "R3", "W", "L1", "L2", "L3"}
    for trace in state.trace.elements.values():
        assert trace.inputs
        assert trace.equations
        assert not trace.intermediates
        assert any("did not converge" in n for n in trace.notes)
    assert state.trace.methods.sections


def test_input_sources_distinguish_user_and_default_values() -> None:
    comps = [
        reservoir("R1", level=20.0),
        tee("T", loss_model="crane"),
        reservoir("R2", level=10.0),
        reservoir("R3", level=12.0),
    ]
    del comps[1]["lossModel"]  # the model default, 'crane'
    conns = [
        connection("L1", ("R1", "port_1"), ("T", "run_inlet"), fittings=[{"type": "exit"}]),
        connection("L2", ("T", "run_outlet"), ("R2", "port_1")),
        connection(
            "L3",
            ("T", "branch"),
            ("R3", "port_1"),
            pipes=[
                {
                    "materialId": "carbon_steel",
                    "schedule": "40",
                    "nominalSize": 4 * 0.0254,
                    "length": 20.0,
                }
            ],
        ),
    ]
    state = solve_project(make_project(comps, conns))
    tee_inputs = {i.name: i for i in state.trace.elements["T"].inputs}
    assert tee_inputs["Loss model"].value == "crane"
    assert tee_inputs["Loss model"].source == "default"
    l1 = {i.name: i for i in state.trace.elements["L1"].inputs}
    assert l1["Fitting 1 (exit) quantity n"].source == "default"
    assert l1["Pipe 1 inner diameter D"].source == "user"
    assert l1["Fluid dynamic viscosity μ"].source == "user"  # a custom fluid
    assert l1["Kinematic viscosity ν = μ/ρ"].source == "computed"
    l3 = {i.name: i for i in state.trace.elements["L3"].inputs}
    assert l3["Pipe 1 inner diameter D"].source == "library"
    assert l3["Pipe 1 roughness ε"].source == "library"
    assert l3["Pipe 1 NPS (library size)"].value == "4"
    sources = {r.name: r.citation for r in state.trace.elements["L3"].data_sources}
    assert "ASME B36.10M" in sources["Pipe 1 inner diameter"]
    assert "Farshad" in sources["Pipe 1 roughness"]


def test_defaults_sent_explicitly_are_labeled_default() -> None:
    """The frontend (apps/web/src/lib/utils/factory.ts) sends every field, defaults included:
    surfacePressure 0, lossModel 'crane', speed 1, status 'on' / 'active', crackingPressure 0,
    siteElevation 0, frictionMethod 'colebrook'. A value equal to the model default is labeled
    'default' (GOALS §4.2), as if the field had been left out; a changed value stays 'user'."""
    curve = {
        "id": "C1",
        "name": "C1",
        "points": [
            {"flow": 0.0, "head": 30.0},
            {"flow": 0.02, "head": 25.0},
            {"flow": 0.04, "head": 15.0},
        ],
    }
    r1 = reservoir("R1", level=5.0)
    r1["surfacePressure"] = 0
    r2 = reservoir("R2", level=10.0)
    r2["surfacePressure"] = 1000.0  # changed: user
    r3 = reservoir("R3", level=8.0)
    t1 = tee("T1", loss_model="crane")
    pump = {
        "type": "pump",
        "id": "P1",
        "name": "P1",
        "elevation": 0.0,
        "curveId": "C1",
        "speed": 1,
        "status": "on",
        "ports": [{"id": "suction", "nominalSize": 0.1}, {"id": "discharge", "nominalSize": 0.1}],
    }
    check = {
        "type": "valve",
        "valveType": "check",
        "id": "CV1",
        "name": "CV1",
        "elevation": 0.0,
        "status": "active",
        "crackingPressure": 0,
        "ports": [{"id": "inlet", "nominalSize": 0.1}, {"id": "outlet", "nominalSize": 0.1}],
    }
    conns = [
        connection("L1", ("R1", "port_1"), ("P1", "suction")),
        connection("L2", ("P1", "discharge"), ("CV1", "inlet")),
        connection("L3", ("CV1", "outlet"), ("T1", "run_inlet")),
        connection("L4", ("T1", "run_outlet"), ("R2", "port_1")),
        connection("L5", ("T1", "branch"), ("R3", "port_1")),
    ]
    project = make_project(
        [r1, r2, r3, t1, pump, check],
        conns,
        pump_library=[curve],
        fluid={"kind": "builtin", "fluidId": "water", "temperature": 293.15},
    )  # project_dict sends siteElevation 0 and frictionMethod 'colebrook', as the frontend does
    state = solve_project(project)
    assert state.converged

    def source(eid: str, name: str) -> str:
        return next(i.source for i in state.trace.elements[eid].inputs if i.name == name)

    assert source("R1", "Surface pressure p_s") == "default"
    assert source("R2", "Surface pressure p_s") == "user"
    assert source("P1", "Speed ratio s") == "default"
    assert source("P1", "Status") == "default"
    assert source("P1", "Site elevation above sea level") == "default"
    assert source("CV1", "Status") == "default"
    assert source("CV1", "Cracking pressure Δp_c") == "default"
    assert source("T1", "Loss model") == "default"
    assert source("L2", "Friction method") == "default"


def test_port_pressures_follow_from_each_element_trace(
    solved: tuple[Project, SolvedState],
) -> None:
    """Valve Δp and the static pressures at valve, tee / wye and pump ports follow from the
    element's own trace: p = ρ g (EGL − z_port − v²/(2g)) with z_port and ρ, g among its
    inputs and EGL, v among its intermediates (M4 review: port elevations were missing)."""
    project, state = solved
    for comp in project.components:
        trace = state.trace.elements[comp.id]
        inputs, values = _inputs(trace), _values(trace)
        if isinstance(comp, IsolationValve | CheckValve | ControlValve):
            if comp.id not in state.valve_results:
                continue
            ports = {
                "inlet": ("EGL at the inlet H1", "Inlet port elevation z_in", "Inlet", "_in"),
                "outlet": ("EGL at the outlet H2", "Outlet port elevation z_out", "Outlet", "_out"),
            }
        elif isinstance(comp, TeeBranch | WyeBranch):
            if comp.id not in state.branch_results:
                continue
            ports = {
                p.id: (f"EGL at {p.id}", f"Port {p.id} elevation z_port", f"Port {p.id}", "")
                for p in comp.ports
            }
        elif isinstance(comp, Pump):
            if comp.id not in state.pump_results:
                continue
            ports = {
                "discharge": (
                    "EGL at the discharge port",
                    "Discharge port elevation z_d",
                    "Discharge",
                    "_d",
                )
            }
        else:
            continue
        rho_g = inputs["Fluid density ρ"] * inputs["Gravitational acceleration g"]
        pressures = {}
        for pid, (egl, z, label, sub) in ports.items():
            node = state.node_results.get(f"{comp.id}:{pid}")
            if node is None:
                continue
            if isinstance(comp, Pump):
                v, p = values[f"{label} velocity v{sub}"], values[f"{label} static pressure p{sub}"]
            else:
                v = values[f"{label} velocity v{sub} (connected pipe)"]
                p = values[f"{label} static pressure p{sub}"]
            g_ = inputs["Gravitational acceleration g"]
            expected = rho_g * (values[egl] - inputs[z] - v * v / (2.0 * g_))
            assert p == pytest.approx(expected, rel=1e-9, abs=1e-6), (comp.id, pid)
            assert p == node.pressure
            pressures[pid] = p
        if "inlet" in pressures and "outlet" in pressures:
            assert values["Static pressure drop Δp"] == pytest.approx(
                pressures["inlet"] - pressures["outlet"], rel=1e-12, abs=1e-9
            )


def test_library_fluid_traces_its_operating_state() -> None:
    """A built-in fluid's trace gives the temperature (and glycol mass fraction) its library
    properties were evaluated at, so ρ and μ can be recomputed from CoolProp (M4 review: the
    water temperature appeared only in the methods summary)."""
    from CoolProp.CoolProp import PropsSI

    _, state = _solve(next(p for p in CASES if p.stem == "library_pipe_builtin_water"))
    inputs = {i.name: i for i in state.trace.elements["L1"].inputs}
    temperature = inputs["Fluid temperature T"]
    assert temperature.unit == "K"
    assert temperature.source == "user"
    t = float(temperature.value)  # type: ignore[arg-type]
    assert inputs["Fluid density ρ"].value == PropsSI("D", "T", t, "P", 101325.0, "Water")
    assert inputs["Fluid dynamic viscosity μ"].value == PropsSI("V", "T", t, "P", 101325.0, "Water")
    sources = {r.name: r.citation for r in state.trace.elements["L1"].data_sources}
    assert f"liquid at {t:g} K, 101325 Pa" in sources["Fluid density (Water)"]

    glycol = make_project(
        [reservoir("R1", level=20.0), reservoir("R2", level=10.0)],
        [connection("L1", ("R1", "port_1"), ("R2", "port_1"))],
        fluid={
            "kind": "builtin",
            "fluidId": "propylene_glycol",
            "temperature": 283.15,
            "concentration": 0.3,
        },
    )
    inputs = {i.name: i for i in solve_project(glycol).trace.elements["L1"].inputs}
    assert inputs["Fluid temperature T"].value == 283.15
    assert inputs["Glycol mass fraction x"].value == 0.3


def test_trace_citations_and_symbols_are_complete() -> None:
    """M4 review: PCHIP cites Fritsch & Butland (scipy's slope formula) with Fritsch &
    Carlson; a PVC pipe's roughness source says it is the closest cited plastic surface; a
    rounded entrance defines rc; the Darby NPS is the schedule-40 interpolation; the NPSHr and
    efficiency curves are written out as PCHIP with their extrapolation or clipping."""
    _, state = _solve(next(p for p in CASES if p.stem == "npsh_cavitation"))
    pump = state.trace.elements["PU1"]
    pchip = next(c for c in pump.correlations if "PchipInterpolator" in c.name)
    assert "Carlson" in pchip.citation
    assert "Butland" in pchip.citation
    pumps = next(s for s in state.trace.methods.sections if s.title == "Pumps")
    assert any("Butland" in r for r in pumps.references)
    assert any(e.startswith("NPSHr₀(Q₀): monotone piecewise cubic (PCHIP)") for e in pump.equations)

    pvc = {"materialId": "pvc", "schedule": "40D1785", "nominalSize": 2 * 0.0254, "length": 10.0}
    comps = [reservoir("R1", level=20.0), reservoir("R2", level=10.0)]
    conns = [
        connection(
            "L1",
            ("R1", "port_1"),
            ("R2", "port_1"),
            pipes=[pvc],
            fittings=[{"type": "entrance_rounded", "radiusRatio": 0.1}],
        )
    ]
    trace = solve_project(make_project(comps, conns)).trace.elements["L1"]
    sources = {r.name: r.citation for r in trace.data_sources}
    assert "fluids has no PVC entry" in sources["Pipe 1 roughness"]
    assert any(e.startswith("rc = radiusRatio · D") for e in trace.equations)
    assert any("rc=" in c.name for c in trace.correlations)

    comps = [
        reservoir("R1", level=10.0),
        reservoir("R2", level=10.0),
        reservoir("R3", level=19.0),
        tee("T", loss_model="crane"),
    ]
    conns = [
        connection("L1", ("T", "run_inlet"), ("R1", "port_1"), length=50.0),
        connection("L2", ("T", "run_outlet"), ("R2", "port_1"), length=50.0),
        connection("L3", ("R3", "port_1"), ("T", "branch"), length=30.0),
    ]
    tee_trace = solve_project(make_project(comps, conns)).trace.elements["T"]
    darby = next(e for e in tee_trace.equations if e.startswith("K = K₁/Re"))
    assert "schedule-40 inner diameter equals D" in darby
    assert "fluids.piping.S40i" in darby


def test_locked_open_check_valve_trace_states_the_law_it_uses() -> None:
    """A check valve locked open has no cracking head (builder: h_c only when 'active'); its
    trace said EGL_in − EGL_out = h_c + K v|v|/(2g) with h_c = Δp_c/(ρg) and listed the cvstatus
    rule, so its numbers contradicted it (M4 review). The trace's own law now reproduces the
    reported head loss."""
    _, state = _solve(next(p for p in CASES if p.stem == "check_valve_locked_open_reverse"))
    trace = state.trace.elements["CV1"]
    values = _values(trace)
    assert any(
        e.startswith("Open (locked): EGL_in − EGL_out = K v|v|/(2g)") for e in trace.equations
    )
    assert not any("h_c = Δp_c" in e for e in trace.equations)
    assert not any("cvstatus" in c.name for c in trace.correlations)
    assert "Cracking head h_c" not in values
    assert any("cracking pressure is not used" in n for n in trace.notes)
    v = values["Velocity v"]
    assert values["Head loss EGL_in − EGL_out"] == pytest.approx(
        values["Fully open K"] * v * abs(v) / (2.0 * g), rel=1e-9
    )
    valves = next(s for s in state.trace.methods.sections if s.title == "Valves")
    assert any(i.startswith("Active check valves: open loss") for i in valves.items)


def test_pipes_and_fittings_are_numbered_from_one_as_in_the_app() -> None:
    """Traces, flags and the notes name a connection's pipes and fittings as the web app
    numbers them (Pipe 1, fitting 1); the flags' segmentIndex / fittingIndex stay 0-based
    indexes into piping.pipes and piping.fittings. Test inputs: an FCV holds the flow at
    Q = 4.712e-5 m³/s so that Re = 4Q/(πDν) is laminar in pipe 1 (D = 0.04 m) and
    transitional in pipe 2 (D = 0.02 m)."""
    fcv = {
        "type": "valve",
        "valveType": "fcv",
        "id": "V1",
        "name": "V1",
        "elevation": 0.0,
        "setpoint": 4.712e-5,
        "ports": [{"id": "inlet", "nominalSize": 0.04}, {"id": "outlet", "nominalSize": 0.04}],
    }
    comps = [reservoir("R1", level=20.0), fcv, reservoir("R2", level=10.0)]
    conns = [
        connection("L1", ("R1", "port_1"), ("V1", "inlet"), length=1.0, diameter=0.04),
        connection(
            "L2",
            ("V1", "outlet"),
            ("R2", "port_1"),
            pipes=[custom_pipe(10.0, 0.04, 4.5e-5), custom_pipe(10.0, 0.02, 4.5e-5)],
            fittings=[
                {"type": "reducer_sudden", "pipeIndex": 0},
                {"type": "elbow_90_lr", "pipeIndex": 1},
                {"type": "gate_valve", "pipeIndex": 0},
            ],
        ),
    ]
    state = solve_project(make_project(comps, conns))
    assert state.converged
    regimes = [s.flow_regime for s in state.link_results["L2"].segments]
    assert regimes == ["laminar", "transitional"]

    trace = state.trace.elements["L2"]
    inputs = _inputs(trace)
    assert inputs["Pipe 1 inner diameter D"] == 0.04
    assert inputs["Pipe 2 inner diameter D"] == 0.02
    assert inputs["Fitting 1 (reducer_sudden) position"] == "between pipes 1 and 2"
    assert inputs["Fitting 2 (elbow_90_lr) position"] == "pipe 2"
    assert inputs["Fitting 3 (gate_valve) position"] == "pipe 1"
    assert not [i.name for i in trace.inputs if i.name.startswith(("Segment", "Fitting 0"))]
    values = _values(trace)
    assert (
        values["Pipe 2 Reynolds number Re"] == state.link_results["L2"].segments[1].reynolds_number
    )
    assert values["Fitting 3 K"] == state.link_results["L2"].fittings[2].k
    reducer = next(n for n in trace.notes if n.startswith("Fitting 1 (reducer_sudden):"))
    # Both directions use the velocity in the smaller pipe, pipe 2 (index 1).
    assert reducer.count("(on pipe 2)") == 2
    assert "segment" not in reducer
    assert any(n.startswith("Pipe 1: laminar") for n in trace.notes)
    assert any(n.startswith("Pipe 2: transitional") for n in trace.notes)

    transitional = next(f for f in state.flags if f.code == "TRANSITIONAL_FLOW")
    assert transitional.details["segmentIndex"] == 1
    assert transitional.message.startswith("connection 'L2' pipe 2: Re = ")
    laminar_k = next(f for f in state.flags if f.code == "CORRELATION_OUT_OF_RANGE")
    assert laminar_k.details["fittingIndex"] == 2
    assert laminar_k.message.startswith("connection 'L2' fitting 3 (gate_valve): its K")


def test_boundary_traces_disclose_entrance_and_exit_losses() -> None:
    """Reservoir and reference-node traces state that no entrance or exit loss is applied
    unless the connection has an entrance or exit fitting, and which ones each port's piping
    has. The statement holds: without such a fitting the port's EGL is the boundary head.
    Levels, pressures and pipes are test inputs."""
    comps = [
        reservoir("R1", level=20.0, ports=("port_1", "port_2")),
        reservoir("R2", level=10.0),
        reference_node("N1", pressure=3.0e5),
    ]
    conns = [
        connection(
            "P1",
            ("R1", "port_1"),
            ("R2", "port_1"),
            fittings=[{"type": "entrance_sharp"}, {"type": "exit"}],
        ),
        connection("P2", ("N1", "port_1"), ("R1", "port_2")),
    ]
    state = solve_project(make_project(comps, conns))
    assert state.converged
    r1 = state.trace.elements["R1"].notes
    n1 = state.trace.elements["N1"].notes
    for notes in (r1, n1, state.trace.elements["R2"].notes):
        assert BOUNDARY_LOSS_NOTE in notes
    assert BOUNDARY_LOSS_NOTE.startswith(
        "No entrance or exit loss is applied where a pipe meets this boundary unless the "
        "connection's piping has an entrance fitting (entrance_sharp, entrance_rounded, "
        "entrance_projecting"
    )
    assert "The web app adds a sharp-edged entrance (entrance_sharp) where new piping" in (
        BOUNDARY_LOSS_NOTE
    )
    assert (
        "Port port_1, connection 'P1': its piping has entrance fitting(s) entrance_sharp and "
        "exit fitting(s) exit."
    ) in r1
    no_fitting = (
        "Port port_2, connection 'P2': its piping has no entrance or exit fitting, so no "
        "entrance or exit loss is applied there."
    )
    assert no_fitting in r1
    assert no_fitting.replace("port_2", "port_1") in n1
    # Without a fitting the port's EGL equals the boundary head (the note's claim); the flow
    # from N1 into R1 is not zero, so the pipes carry a velocity head.
    assert state.link_results["P2"].flow != 0
    assert state.node_results["N1:port_1"].egl == state.boundary_results["N1"].egl
    assert state.node_results["R1:port_2"].egl == state.boundary_results["R1"].egl
