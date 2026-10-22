"""Self-checks of the reference cases themselves, independent of the solver.

- Friction-factor paths: Colebrook (Lambert W) against Clamond; the constants and slopes used in
  the transition interpolation; the Hermite transition against EPANET 2.2's own Dunlop
  polynomial when fed EPANET's Swamee–Jain.
- Every case file: a valid Project; energy equations of every connection and the law of every
  pump, valve and Crane branch re-evaluated from the *project JSON* close with the expected
  values; every pump and valve state is the one design §5's status rules select; continuity
  holds; ideal-branch ports share one EGL and only isolated ports lack one; expected pressures
  follow p = ρ g (H − z − v²/2g).
- Second routes to the answers: the parallel split by nested brentq (the case uses fsolve), a
  whole-network fsolve of every case from a perturbed start, NPSH available from the absolute
  suction pressure, the PRV/PSV static setpoint at its port, the dead tee branch read as
  converging, and the pump curve's end-slope extension.
- Sources: the Cv/Kv definitions against fluids' converters and Crane's 891 d⁴/Cv²; the reference
  water density against fluids' documented value; the Crane tee functions against their
  docstring examples (Crane TP-410 Examples 7-35, 7-36).
- EPANET cases: residuals vanish under EPANET's constants (g = 32.2 ft/s², minor-loss constant
  0.02517, its friction code) to float32 precision, and our model's answer stays well inside the
  0.5 % criterion of EPANET's.
"""

import math
from pathlib import Path
from typing import Any

import fluids.fittings
import fluids.friction
import numpy as np
import pytest
from scipy.constants import inch
from scipy.optimize import brentq

from opensolve_pipe.models.components import (
    ControlValve,
    FlowCoefficient,
    Pump,
    TeeBranch,
    WyeBranch,
)
from opensolve_pipe.models.project import Project
from tests.reference import derivations as dv
from tests.reference import derivations_branches as dvb
from tests.reference import element_laws as el
from tests.reference import network_check as nc
from tests.reference.case_format import case_files, case_path, read_case

FLOAT32_REL = 2.0**-23
CASES = case_files()
RE_GRID = (4.0e3, 1.0e4, 1.0e5, 1.0e6, 1.0e7)
ED_GRID = (0.0, 1.0e-6, 1.0e-4, 1.0e-3, 1.0e-2)


def _load(path: Path) -> tuple[dict[str, Any], Project]:
    case = read_case(path)
    return case, Project.model_validate(case["project"])


def _is_epanet(case: dict[str, Any]) -> bool:
    source: str = case["source"]
    return source.startswith("WNTR ")


# --- Friction factor ---------------------------------------------------------------------------


@pytest.mark.parametrize("re", RE_GRID)
@pytest.mark.parametrize("ed", ED_GRID)
def test_colebrook_lambert_w_agrees_with_clamond(re: float, ed: float) -> None:
    # Two solution methods of the same equation (Lambert W here, Clamond 2009 in the solver).
    assert dv.colebrook(re, ed) == pytest.approx(fluids.friction.Clamond(re, ed), rel=1.0e-12)


@pytest.mark.parametrize("re", RE_GRID)
@pytest.mark.parametrize("ed", ED_GRID)
def test_colebrook_constants_and_slope(re: float, ed: float) -> None:
    f = dv.colebrook(re, ed)
    # fluids' value satisfies the equation with the constants used for the analytic slope.
    lhs = 1.0 / math.sqrt(f)
    rhs = -2.0 * math.log10(ed / dv.COLEBROOK_A + dv.COLEBROOK_B / (re * math.sqrt(f)))
    assert lhs == pytest.approx(rhs, rel=1.0e-12)
    step = re * 1.0e-5
    centered = (dv.colebrook(re + step, ed) - dv.colebrook(re - step, ed)) / (2.0 * step)
    assert dv.colebrook_dfdre(re, ed) == pytest.approx(centered, rel=1.0e-6)


@pytest.mark.parametrize("re", RE_GRID)
@pytest.mark.parametrize("ed", ED_GRID[1:])
def test_swamee_jain_form_and_slope(re: float, ed: float) -> None:
    y = (dv.SWAMEE_JAIN_C / re) ** dv.SWAMEE_JAIN_N + ed / dv.SWAMEE_JAIN_A
    assert dv.swamee_jain(re, ed) == pytest.approx(0.25 / math.log10(y) ** 2, rel=1.0e-13)
    step = re * 1.0e-5
    centered = (dv.swamee_jain(re + step, ed) - dv.swamee_jain(re - step, ed)) / (2.0 * step)
    assert dv.swamee_jain_dfdre(re, ed) == pytest.approx(centered, rel=1.0e-6)


def _epanet_swamee_jain(re: float, ed: float) -> float:
    """EPANET's turbulent formula (hydcoeffs.c:644-650), written in Re."""
    return nc.epanet_friction_factor(max(re, dv.RE_TURBULENT), ed)


def _epanet_swamee_jain_dfdre(re: float, ed: float) -> float:
    """d/dRe of f = 1/(A9 ln y)², y = ε/D/3.7 + 5.74 Re^-0.9 (the form behind A8, AB in
    hydcoeffs.c:27-30): df/dRe = −2 A9 (dy/dRe)/(y (A9 ln y)³), dy/dRe = −0.9·5.74 Re^-1.9."""
    y = ed / 3.7 + 5.74 * re**-0.9
    dydre = -0.9 * 5.74 * re**-1.9
    return float(-2.0 * nc.EPANET_A9 * dydre / (y * (nc.EPANET_A9 * math.log(y)) ** 3))


@pytest.mark.parametrize("ed", ED_GRID)
def test_hermite_transition_reproduces_epanet_dunlop_polynomial(ed: float) -> None:
    # Dunlop's polynomial in EPANET 2.2 (hydcoeffs.c:653-667) is the Hermite cubic of design
    # §2.1 with EPANET's Swamee–Jain at Re = 4000; our independent Hermite must reproduce it.
    f_end = _epanet_swamee_jain(dv.RE_TURBULENT, ed)
    slope_end = _epanet_swamee_jain_dfdre(dv.RE_TURBULENT, ed)
    for re in np.linspace(2000.0 + 1.0e-6, 4000.0 - 1.0e-6, 41):
        ours = dv.transition_friction_factor(float(re), f_end, slope_end)
        assert ours == pytest.approx(nc.epanet_friction_factor(float(re), ed), rel=1.0e-12)


@pytest.mark.parametrize("method", ["colebrook", "swamee_jain"])
@pytest.mark.parametrize("ed", ED_GRID)
def test_friction_factor_is_continuous_at_the_regime_bounds(method: Any, ed: float) -> None:
    def f(re: float) -> float:
        return dv.friction_factor(re, ed, method)

    for bound in (dv.RE_LAMINAR, dv.RE_TURBULENT):
        below, above = f(bound * (1.0 - 1.0e-12)), f(bound)
        assert below == pytest.approx(above, rel=1.0e-9)
        # Slopes match too (C1 Hermite end conditions).
        step = bound * 1.0e-6
        left = (f(bound - step) - f(bound - 2.0 * step)) / step
        right = (f(bound + 2.0 * step) - f(bound + step)) / step
        assert left == pytest.approx(right, rel=1.0e-3)


# --- Case files ----------------------------------------------------------------------------------


@pytest.mark.parametrize("path", CASES, ids=lambda p: p.stem)
def test_case_project_validates_and_round_trips(path: Path) -> None:
    case, project = _load(path)
    assert project.model_dump(mode="json", exclude_none=True) == case["project"]
    assert path == case_path(case["name"])


@pytest.mark.parametrize("path", CASES, ids=lambda p: p.stem)
def test_energy_equations_close(path: Path) -> None:
    case, project = _load(path)
    expected = case["expected"]
    flows, egl = expected["flows"], expected["egl"]
    q_max = max(abs(q) for q in flows.values())
    if _is_epanet(case):
        model = nc.EPANET_MODEL
        nu = nc.kinematic_viscosity(project)
        losses = [
            abs(nc.connection_head_loss(c, flows[c.id], nu, model)) for c in project.connections
        ]
        # float32 rounding of the heads and flows EPANET reports, with a few ulps of margin.
        heads = max(abs(h) for h in egl.values())
        tolerance = 8 * FLOAT32_REL * (heads + max(losses))
        # EPANET's GPM unit constant biases flows by about -3.8e-7 relative (source text).
        flow_tolerance = 8 * FLOAT32_REL * q_max
    else:
        model = nc.our_model(project)
        tolerance = 1.0e-11
        flow_tolerance = 1.0e-15 * q_max
    residuals = nc.energy_residuals(project, flows, egl, model)
    # Every connection outside an isolated section has both EGLs and is checked.
    isolated = nc.isolated_ports(project, nc.element_states(project, expected))
    checked = {
        c.id
        for c in project.connections
        if f"{c.from_component_id}:{c.from_port_id}" not in isolated
    }
    assert set(residuals) == checked
    assert max(abs(r) for r in residuals.values()) <= tolerance, residuals
    laws = nc.element_residuals(
        project, flows, egl, nc.element_states(project, expected), model, nc.held_split_ks(expected)
    )
    assert all(abs(r) <= tolerance for r in laws.heads.values()), laws.heads
    assert all(abs(r) <= flow_tolerance for r in laws.flows.values()), laws.flows


@pytest.mark.parametrize(
    "path",
    [p for p in CASES if {"pumps", "valves"} & set(read_case(p)["expected"])],
    ids=lambda p: p.stem,
)
def test_element_states_follow_the_status_rules(path: Path) -> None:
    """Each expected pump status and valve state is the one the status rules of design §5
    select at the expected solution (margin −htol: the rules exactly)."""
    case, project = _load(path)
    expected = case["expected"]
    states = nc.element_states(project, expected)
    epanet = _is_epanet(case)
    problems = nc.state_problems(
        project,
        expected["flows"],
        expected["egl"],
        states,
        -el.HTOL,
        8 * FLOAT32_REL if epanet else 1.0e-12,
        nc.EPANET_FCV_LEAK if epanet else 0.0,
    )
    assert not problems, problems


@pytest.mark.parametrize("path", CASES, ids=lambda p: p.stem)
def test_expected_flows_satisfy_continuity(path: Path) -> None:
    case, project = _load(path)
    flows = case["expected"]["flows"]
    q_max = max(abs(q) for q in flows.values())
    relative = 8 * FLOAT32_REL if _is_epanet(case) else 1.0e-15
    for component_id, net in nc.net_inflow(project, flows).items():
        assert abs(net) <= relative * q_max, component_id


@pytest.mark.parametrize("path", CASES, ids=lambda p: p.stem)
def test_ideal_tee_ports_share_one_egl(path: Path) -> None:
    case, project = _load(path)
    egl = case["expected"]["egl"]
    for component in project.components:
        if isinstance(component, TeeBranch | WyeBranch) and component.loss_model == "ideal":
            values = {egl[f"{component.id}:{p.id}"] for p in component.ports}
            assert len(values) == 1, component.id
    # Every port of the project has an expected EGL, except ports in an isolated section.
    isolated = nc.isolated_ports(project, nc.element_states(project, case["expected"]))
    ports = {f"{c.id}:{p.id}" for c in project.components for p in c.ports}
    assert set(egl) == ports - isolated
    expects_isolation = any(
        f["code"] == "ISOLATED_SECTION" for f in case["expected"].get("flags", [])
    )
    assert bool(isolated) == expects_isolation


@pytest.mark.parametrize(
    "path", [p for p in CASES if "pressures" in read_case(p)["expected"]], ids=lambda p: p.stem
)
def test_expected_pressures_follow_the_definition(path: Path) -> None:
    case, project = _load(path)
    expected = case["expected"]
    rho = nc.density(project)
    for key, pressure in expected["pressures"].items():
        v = nc.end_velocity(project, key, expected["flows"])
        z = nc.port_elevation(project, key)
        assert pressure == pytest.approx(
            dv.static_pressure(rho, expected["egl"][key], z, v), rel=1.0e-12, abs=1.0e-9
        ), key


def test_fluid_properties_recorded() -> None:
    for path in CASES:
        case, project = _load(path)
        fluid = case["expected"]["fluid"]
        assert fluid["density"] == nc.density(project)
        assert fluid["dynamicViscosity"] / fluid["density"] == pytest.approx(
            nc.kinematic_viscosity(project), rel=1.0e-15
        )
        if "vaporPressure" in fluid:
            assert fluid["vaporPressure"] == nc.fluid_state(project)[2]


def test_glycol_and_override_properties_come_from_their_sources() -> None:
    """Glycols: CoolProp INCOMP gives no vapor pressure, so it is null; an override replaces
    exactly its own property and leaves the CoolProp density."""
    for name in ("fluid_meg_solution", "fluid_mpg_solution_laminar"):
        case, _ = _load(case_path(name))
        assert case["expected"]["fluid"]["vaporPressure"] is None
        assert {"code": "NO_VAPOR_PRESSURE"} in case["expected"]["flags"]
    case, project = _load(case_path("fluid_property_override"))
    fluid = project.fluid
    assert fluid.kind == "builtin"
    assert fluid.overrides is not None
    assert fluid.concentration is not None
    rho, mu = dv.glycol_properties(fluid.fluid_id, fluid.temperature, fluid.concentration)
    expected = case["expected"]["fluid"]
    assert expected["density"] == rho
    assert expected["dynamicViscosity"] == fluid.overrides.dynamic_viscosity != mu
    assert expected["vaporPressure"] == fluid.overrides.vapor_pressure


# --- Second routes to the answers ------------------------------------------------------------


def test_parallel_split_by_nested_brentq() -> None:
    """The parallel case solved a second way: for a trial total Q, brentq splits it so the two
    paths lose the same head; an outer brentq finds the Q that uses up H1 − H2."""
    case, project = _load(case_path("parallel_pipes_ideal_tees"))
    nu = nc.kinematic_viscosity(project)
    model = nc.our_model(project)
    conn = {c.id: c for c in project.connections}
    heads = nc.fixed_heads(project)

    def h(cid: str, q: float) -> float:
        return nc.connection_head_loss(conn[cid], q, nu, model)

    def split(q: float) -> float:
        return float(brentq(lambda qa: h("LA", qa) - h("LB", q - qa), 0.0, q, xtol=1e-18))

    def energy(q: float) -> float:
        qa = split(q)
        return heads["R1:port_1"] - heads["R2:port_1"] - (h("LIN", q) + h("LA", qa) + h("LOUT", q))

    q = float(brentq(energy, 1.0e-4, 1.0, xtol=1e-18, rtol=1e-15))
    qa = split(q)
    flows = case["expected"]["flows"]
    assert q == pytest.approx(flows["LIN"], rel=1.0e-10)
    assert qa == pytest.approx(flows["LA"], rel=1.0e-10)
    assert q - qa == pytest.approx(flows["LB"], rel=1.0e-10)


@pytest.mark.parametrize(
    "path", [p for p in CASES if not p.stem.startswith("epanet")], ids=lambda p: p.stem
)
def test_network_solve_reproduces_closed_form_case(path: Path) -> None:
    case, project = _load(path)
    expected = case["expected"]
    guess_q = {k: 1.2 * q + 1.0e-4 for k, q in expected["flows"].items()}
    guess_h = {k: h + 0.3 for k, h in expected["egl"].items()}
    states = nc.element_states(project, expected)
    held = nc.held_pairs(project, expected["flows"])
    flows, egl = nc.solve_network(
        project,
        nc.our_model(project),
        guess_q,
        guess_h,
        states,
        held,
        nc.held_split_ks(expected),
    )
    for key, q in expected["flows"].items():
        assert flows[key] == pytest.approx(q, rel=1.0e-9, abs=1.0e-15), key
    assert set(egl) == set(expected["egl"])
    for key, h in expected["egl"].items():
        assert egl[key] == pytest.approx(h, abs=1.0e-9), key


def _has_components(path: Path) -> bool:
    return bool({"pumps", "valves"} & set(read_case(path)["expected"]))


EPANET_CASES = [p for p in CASES if p.stem.startswith("epanet")]


@pytest.mark.parametrize(
    "path", [p for p in EPANET_CASES if not _has_components(p)], ids=lambda p: p.stem
)
def test_epanet_case_agrees_with_our_model_inside_the_criterion(path: Path) -> None:
    """Our model (g = 9.80665, exact minor-loss constant, fluids' Swamee–Jain) solved as a
    network lands within 0.2 % of EPANET in every flow and 1 mm in every head, so EPANET's
    built-in constants use well under half of the 0.5 % criterion."""
    case, project = _load(path)
    expected = case["expected"]
    flows, egl = nc.solve_network(
        project,
        nc.our_model(project),
        expected["flows"],
        expected["egl"],
        nc.element_states(project, expected),
    )
    for key, q in expected["flows"].items():
        assert flows[key] == pytest.approx(q, rel=2.0e-3), key
    for key, h in expected["egl"].items():
        assert egl[key] == pytest.approx(h, abs=1.0e-3), key


@pytest.mark.parametrize(
    "path", [p for p in EPANET_CASES if _has_components(p)], ids=lambda p: p.stem
)
def test_epanet_component_case_agrees_with_our_model_inside_half_the_criterion(
    path: Path,
) -> None:
    """Pump and control-valve networks: heads next to a pump or a fixed-flow valve are not
    pinned by reservoirs, so EPANET's g = 32.2 ft/s² (0.08 % in every head loss) moves them by
    a few mm (measured: up to 1.9 mm at the pump, 6.9 mm at the FCV). Our model still lands
    inside half of the D6 criterion: flows within 0.25 %, every EGL and every connection's
    EGL drop within max(0.25 %, 5 mm). Solving with EPANET's constants instead reproduces EPANET
    to float32 precision (test_energy_equations_close)."""
    case, project = _load(path)
    expected = case["expected"]
    flows, egl = nc.solve_network(
        project,
        nc.our_model(project),
        expected["flows"],
        expected["egl"],
        nc.element_states(project, expected),
    )
    half_floor = 0.5 * 0.01  # m, half of the D6 head floor
    for key, q in expected["flows"].items():
        assert flows[key] == pytest.approx(q, rel=2.5e-3), key
    for key, h in expected["egl"].items():
        assert egl[key] == pytest.approx(h, rel=2.5e-3, abs=half_floor), key
    for c in project.connections:
        a, b = f"{c.from_component_id}:{c.from_port_id}", f"{c.to_component_id}:{c.to_port_id}"
        want = expected["egl"][a] - expected["egl"][b]
        assert egl[a] - egl[b] == pytest.approx(want, rel=2.5e-3, abs=half_floor), c.id


def test_cases_cover_the_intended_flow_regimes() -> None:
    def regimes(name: str) -> set[str]:
        case, project = _load(case_path(name))
        nu = nc.kinematic_viscosity(project)
        found: set[str] = set()
        for c in project.connections:
            q = case["expected"]["flows"][c.id]
            for pipe in c.piping.pipes:
                if q != 0.0:
                    found.add(dv.regime(dv.reynolds(q, nc.resolve_pipe(pipe)[0], nu)))
        return found

    assert regimes("single_pipe_laminar") == {"laminar"}
    assert regimes("fluid_mpg_solution_laminar") == {"laminar"}
    assert regimes("transitional_flow_colebrook") == {"transitional"}
    assert regimes("single_pipe_turbulent") == {"turbulent"}
    assert regimes("epanet_looped_network_b") == {"laminar", "transitional", "turbulent"}


# --- M3 second routes and sources ---------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [p for p in CASES if "npshAvailable" in str(read_case(p)["expected"].get("pumps"))],
    ids=lambda p: p.stem,
)
def test_npsh_from_absolute_suction_pressure(path: Path) -> None:
    """NPSHa a second way (TSD §5.5 form): p_abs/(ρg) + v_s²/(2g) − p_vap/(ρg), with p_abs the
    expected static gauge pressure at the suction port plus the atmospheric pressure, which is
    the override if set and ATMOSPHERE_1976(siteElevation) otherwise; margin = NPSHa − NPSHr."""
    case, project = _load(path)
    expected = case["expected"]
    rho, _, p_vap = nc.fluid_state(project)
    assert p_vap is not None
    settings = project.settings
    p_atm = (
        settings.atmospheric_pressure
        if settings.atmospheric_pressure is not None
        else dv.standard_atmosphere_pressure(settings.site_elevation)
    )
    assert expected["atmosphericPressure"] == p_atm
    for pump in (c for c in project.components if isinstance(c, Pump)):
        want = expected["pumps"][pump.id]
        key = f"{pump.id}:suction"
        v = nc.end_velocity(project, key, expected["flows"])
        p_abs = expected["pressures"][key] + p_atm
        npsha = p_abs / (rho * dv.G) + v * v / (2.0 * dv.G) - p_vap / (rho * dv.G)
        assert want["npshAvailable"] == pytest.approx(npsha, rel=1.0e-12)
        assert want["npshMargin"] == pytest.approx(
            want["npshAvailable"] - want["npshRequired"], rel=1.0e-12, abs=1.0e-12
        )
        cavitating = {"code": "CAVITATION", "componentId": pump.id} in expected.get("flags", [])
        assert cavitating == (want["npshMargin"] < 0.0)


def test_siphon_crest_is_below_vapor_pressure() -> None:
    case, _ = _load(case_path("siphon_high_point_below_vapor_pressure"))
    expected = case["expected"]
    p_vap = expected["fluid"]["vaporPressure"]
    for key in ("T1:run_inlet", "T1:run_outlet", "T1:branch", "P1:port_1"):
        assert expected["pressures"][key] + expected["atmosphericPressure"] < p_vap, key
    # The supply-side reservoir port is a quiescent boundary well above the vapor pressure.
    assert expected["atmosphericPressure"] > p_vap


@pytest.mark.parametrize(
    "path",
    [p for p in CASES if "valves" in read_case(p)["expected"]],
    ids=lambda p: p.stem,
)
def test_active_prv_psv_hold_the_static_setpoint(path: Path) -> None:
    """Our PRV/PSV semantics (design §5.3): the static gauge pressure at the outlet (PRV) or
    inlet (PSV) port equals the setpoint, with v in the pipe on that port; for EPANET cases this
    checks the setting iteration (float32 heads)."""
    case, project = _load(path)
    expected = case["expected"]
    rho = nc.density(project)
    for valve in project.components:
        if not (
            isinstance(valve, ControlValve)
            and valve.valve_type in ("prv", "psv")
            and expected["valves"][valve.id]["state"] == "active"
        ):
            continue
        key = f"{valve.id}:{'outlet' if valve.valve_type == 'prv' else 'inlet'}"
        v = nc.end_velocity(project, key, expected["flows"])
        p = dv.static_pressure(rho, expected["egl"][key], nc.port_elevation(project, key), v)
        tolerance = 8 * FLOAT32_REL * expected["egl"][key] if _is_epanet(case) else 1.0e-9
        assert p == pytest.approx(valve.setpoint, abs=rho * dv.G * tolerance)


def test_dead_tee_branch_reads_the_same_as_converging() -> None:
    """A dead branch is both 'diverging with q = 0' and 'converging with q = 0' (design §5.4); at
    β² ≤ 0.35 the two Crane readings give the same branch EGL, so the case is unambiguous."""
    case, project = _load(case_path("tee_crane_dead_branch"))
    expected = case["expected"]
    d_run = nc.port_diameter(project, "T1:run_inlet")
    d_branch = nc.port_diameter(project, "T1:branch")
    assert (d_branch / d_run) ** 2 <= 0.35
    q = expected["flows"]["L1"]
    diverging = expected["egl"]["T1:branch"] - expected["egl"]["T1:run_inlet"]
    assert diverging == pytest.approx(
        dvb.dead_branch_converging_reading(d_run, d_branch, q), rel=1.0e-12
    )
    # The dead branch sits at the run's static head: p(branch) = p(run_inlet).
    assert expected["pressures"]["T1:branch"] == pytest.approx(
        expected["pressures"]["T1:run_inlet"], rel=1.0e-12
    )


@pytest.mark.parametrize(
    "path", [p for p in CASES if "stepHolds" in read_case(p)["expected"]], ids=lambda p: p.stem
)
def test_step_hold_splits_are_the_two_cycle_of_the_tangent_update(path: Path) -> None:
    """A K held across a Crane step (design §5.4), re-derived from the project JSON with the
    whole-network solve: the fluids K jumps by more than 1e-4 at the step; the outer update
    (K linearized about the last split, ``el.tangent_k``) maps splitA to splitB and back, one
    on each side of the step; with the held K the solved split stays between them; the branch
    is flagged CORRELATION_OUT_OF_RANGE."""
    case, project = _load(path)
    expected = case["expected"]
    states = nc.element_states(project, expected)
    model = nc.our_model(project)
    for cid, hold in nc.step_holds(expected).items():
        assert {"code": "CORRELATION_OUT_OF_RANGE", "componentId": cid} in expected["flags"]
        branch = nc.component_of(project, cid)
        assert isinstance(branch, TeeBranch | WyeBranch)

        def split(rule: el.SplitK, branch: TeeBranch | WyeBranch = branch) -> tuple[float, bool]:
            flows, _ = nc.solve_network(
                project, model, expected["flows"], expected["egl"], states, (), {branch.id: rule}
            )
            inflows = {
                p.id: nc.port_inflow(project, f"{branch.id}:{p.id}", flows) for p in branch.ports
            }
            losses = nc.branch_offsets(project, branch, inflows)
            assert losses.combined_port is not None
            diverging = inflows[losses.combined_port] > 0.0
            return el.q_ratio(losses, inflows, nc.branch_kind(branch)), diverging

        q_held, diverging = split(hold.rule())
        assert hold.split_a <= hold.step < hold.split_b
        assert hold.split_a < q_held < hold.split_b
        inflows = {
            p.id: nc.port_inflow(project, f"{branch.id}:{p.id}", expected["flows"])
            for p in branch.ports
        }
        combined = nc.branch_offsets(project, branch, inflows).combined_port
        assert combined is not None
        others = [p.id for p in branch.ports if p.id != combined]
        d_branch = nc.port_diameter(project, f"{cid}:{el.BRANCH_PORT[nc.branch_kind(branch)]}")
        assert el.BRANCH_PORT[nc.branch_kind(branch)] in others
        geometry = el.CraneGeometry(
            nc.branch_angle(branch),
            nc.port_diameter(project, f"{cid}:{combined}"),
            d_branch,
            diverging,
        )
        below, above = geometry.k(hold.step), geometry.k(float(np.nextafter(hold.step, 1.0)))
        assert max(abs(a - b) for a, b in zip(above, below, strict=True)) > 1.0e-4
        assert split(el.tangent_k(hold.split_a))[0] == pytest.approx(hold.split_b, abs=1.0e-9)
        assert split(el.tangent_k(hold.split_b))[0] == pytest.approx(hold.split_a, abs=1.0e-9)


def test_bullhead_tee_uses_the_darby_fallback_on_each_leg() -> None:
    case, project = _load(case_path("tee_crane_bullhead_fallback"))
    expected = case["expected"]
    nu = nc.kinematic_viscosity(project)
    for port in ("run_inlet", "run_outlet"):
        key = f"T1:{port}"
        d = nc.port_diameter(project, key)
        v = nc.end_velocity(project, key, expected["flows"])
        k = (expected["egl"]["T1:branch"] - expected["egl"][key]) / (v * v / (2.0 * dv.G))
        darby = fluids.fittings.Darby3K(Di=d, Re=abs(v) * d / nu, name=el.TEE_FALLBACK_DARBY_NAME)
        assert k == pytest.approx(darby, rel=1.0e-12)
    assert {"code": "TEE_PATTERN_FALLBACK", "componentId": "T1"} in expected["flags"]


def test_crane_tee_functions_reproduce_their_docstring_examples() -> None:
    """fluids 1.3.1 docstring examples (Crane TP-410 2009 Examples 7-35 and 7-36; values as the
    research notes fluids_reference.md §1.8.3 record them)."""
    ff = fluids.fittings
    assert ff.K_branch_converging_Crane(0.1023, 0.1023, 0.018917, 0.00633) == pytest.approx(
        -0.04044108513625682, rel=1.0e-12
    )
    assert ff.K_run_converging_Crane(0.1023, 0.1023, 0.018917, 0.00633) == pytest.approx(
        0.32575847854551254, rel=1.0e-12
    )
    assert ff.K_branch_diverging_Crane(0.146, 0.146, 0.02525, 0.01583, angle=45) == pytest.approx(
        0.4639895627496694, rel=1.0e-12
    )
    assert ff.K_run_diverging_Crane(0.146, 0.146, 0.02525, 0.01583, angle=45) == pytest.approx(
        -0.06810067607153049, rel=1.0e-12
    )


def test_pump_curve_fit_passes_the_points_and_extends_with_the_end_slope() -> None:
    from tests.reference.derivations_pumps import curve_a

    curve = curve_a()
    fit = el.head_fit(curve)
    for point in curve.points:
        assert fit.value(point.flow) == pytest.approx(point.head, rel=1.0e-14)
    # Beyond the last point: a straight line, continuous in value and slope (design §2.2).
    q_max = curve.points[-1].flow
    slope = fit.slope(q_max)
    for dq in (1.0e-3, 5.0e-3, 2.0e-2):
        assert fit.value(q_max + dq) == pytest.approx(
            curve.points[-1].head + slope * dq, rel=1.0e-14
        )
    step = 1.0e-7
    left = (fit.value(q_max) - fit.value(q_max - step)) / step
    assert left == pytest.approx(slope, rel=1.0e-4)
    # Affinity laws: H(Q) = s² H₀(Q/s).
    assert el.pump_head(curve, 0.8, 0.016) == pytest.approx(0.64 * fit.value(0.02), rel=1e-14)
    case, _ = _load(case_path("pump_beyond_curve_extrapolation"))
    q = case["expected"]["pumps"]["PU1"]["operatingFlow"]
    assert q > q_max
    assert case["expected"]["pumps"]["PU1"]["operatingHead"] == pytest.approx(
        curve.points[-1].head + slope * (q - q_max), rel=1.0e-12
    )


def test_collinear_epanet_pump_curve_is_its_own_pchip() -> None:
    """EPANET interpolates a 4-point curve piecewise linearly (design §11): for collinear points
    PCHIP is the same straight line, inside the points and beyond them."""
    _, project = _load(case_path("epanet_pump_network"))
    curve = project.pump_library[0]
    fit = el.head_fit(curve)
    (q0, h0), (q1, h1) = [(p.flow, p.head) for p in curve.points[:2]]
    slope = (h1 - h0) / (q1 - q0)
    for q in np.linspace(-0.01, 0.08, 37):
        assert fit.value(float(q)) == pytest.approx(h0 + slope * (float(q) - q0), rel=1.0e-12)


def test_reference_water_density_matches_the_fluids_docstring() -> None:
    """CoolProp IAPWS-95 water at 60 °F and 703572 Pa against the density the fluids
    Kv_to_K docstring prints for the same conditions (999.29744568 kg/m³)."""
    documented = 999.29744568
    assert pytest.approx(documented, rel=1.0e-8) == el.REFERENCE_WATER_DENSITY


@pytest.mark.parametrize("nps", [2.0, 4.0, 8.0])
def test_cv_kv_definitions_agree_with_fluids_and_crane(nps: float) -> None:
    """K from the Cv and Kv definitions (element_laws) against fluids.fittings.Cv_to_K and
    Kv_to_K (ISA-75.01.01), and the Cv form against Crane's K = 891 d⁴/Cv² (d in inches; the
    coefficient TSD §5.3 quotes) within 0.2 %."""
    d = dv.carbon_steel_schedule_40(nps)[0]
    for value in (10.0, 100.0, 1000.0):
        cv = el.k_from_flow_coefficient(FlowCoefficient(kind="Cv", value=value), d)
        kv = el.k_from_flow_coefficient(FlowCoefficient(kind="Kv", value=value), d)
        assert cv == pytest.approx(float(fluids.fittings.Cv_to_K(value, d)), rel=2.0e-6)
        assert kv == pytest.approx(float(fluids.fittings.Kv_to_K(value, d)), rel=2.0e-6)
        assert cv * value**2 / (d / inch) ** 4 == pytest.approx(891.0, rel=2.0e-3)
