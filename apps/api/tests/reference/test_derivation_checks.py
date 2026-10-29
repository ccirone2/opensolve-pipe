"""Self-checks of the reference cases themselves, independent of the solver.

- Friction-factor paths: Colebrook (Lambert W) against Clamond; the constants and slopes used in
  the transition interpolation; the Hermite transition against EPANET 2.2's own Dunlop
  polynomial when fed EPANET's Swamee–Jain.
- Every case file: a valid Project; energy equations of every connection and the law of every
  pump, valve and Crane branch re-evaluated from the *project JSON* close with the expected
  values; every pump and valve state is the one design §5's status rules select; continuity
  holds (an assigned-flow node withdrawing its flow); ideal-branch ports share one EGL and only
  isolated ports lack one; expected pressures follow p = ρ g (H − z − v²/2g).
- Second routes to the answers: the parallel split by nested brentq (the case uses fsolve), a
  whole-network fsolve of every case from a perturbed start, NPSH available from the absolute
  suction pressure, the PRV/PSV static setpoint at its port, the dead tee branch read as
  converging, and the pump curve's end-slope extension.
- Sources: the Cv/Kv definitions against fluids' converters and Crane's 891 d⁴/Cv²; the reference
  water density against fluids' documented value; the Crane tee functions against their
  docstring examples (Crane TP-410 Examples 7-35, 7-36).
- EPANET cases: residuals vanish under EPANET's constants (g = 32.2 ft/s², minor-loss constant
  0.02517, its friction code; an orifice plate's GPV curve) to float32 precision, and our model's
  answer stays well inside the 0.5 % criterion of EPANET's.
- Orifice plates (docs/proposals/orifice-plate.md): the suite's transcription of ISO 5167-2 eq.
  (4) against fluids and its docstring examples, K against the pressure-loss relation, Borda–
  Carnot and Skelton's ratio, the cancellation-free K, the hold; each case's results, flags and
  coefficients from their definitions; the meter's reading read back by fluids' meter solver;
  C held at another Re missing C7 and E3 beyond D6; the move of an entered C in C12; and the
  proposal's measured values.
- Pressure relief valves (docs/proposals/pressure-relief-valve.md): the suite's band root
  against a 60-digit Newton solve and the forward law; continuity and the slope step at full
  lift (the least band slope op/(2 + 3op)); the full-lift equation against fluids'
  ``API520_A_l`` for every letter (its rounded 11.78, +6.09×10⁻⁵); the covering letter against
  ``API520_round_size``; ASME's default overpressure and scope; the published x-relief-data
  against the suite's own constants; each case's results and flags from their definitions; the
  other pressure readings on C2; the EPANET cases against the closed form; and the proposal's
  measured values.
"""

import decimal
import itertools
import math
from pathlib import Path
from typing import Any

import fluids.fittings
import fluids.friction
import fluids.safety_valve
import numpy as np
import pytest
from scipy.constants import inch
from scipy.optimize import brentq

from opensolve_pipe.models.components import (
    ControlValve,
    FlowCoefficient,
    Orifice,
    OrificeTaps,
    Pump,
    PumpControl,
    ReliefValve,
    TeeBranch,
    WyeBranch,
    relief_data_extension,
)
from opensolve_pipe.models.project import Project
from tests.reference import derivations as dv
from tests.reference import derivations_branches as dvb
from tests.reference import derivations_orifice as do
from tests.reference import derivations_relief as dr
from tests.reference import element_laws as el
from tests.reference import network_check as nc
from tests.reference.case_format import case_files, case_path, custom_fluid, read_case

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
    # Float64 heads resolve an energy equation only to a few ulps of its largest term
    # (``nc.energy_round_off``, the stop test's allowance from METHOD_VERSION 1.2.0). That is
    # below every case's tolerance up to 1.1e4 m of head, so the bound changes only in
    # round_off_large_heads, whose heads of 4e9 m are 4.8e-7 m apart.
    round_off = nc.energy_round_off(project, flows, egl, model)
    bounds = {cid: max(tolerance, round_off[cid]) for cid in residuals}
    assert all(abs(r) <= bounds[cid] for cid, r in residuals.items()), (residuals, bounds)
    # A flow-controlled pump is checked by its fixed flow, except in EPANET cases, whose
    # reference runs are EPANET's own pump law (at the expected speed) or the FAQ substitute
    # (whose closed pump EPANET lets pass Δh/CBIG): there by its head law at that speed.
    law_project, states = (
        nc.at_expected_speeds(project, expected)
        if _is_epanet(case)
        else (project, nc.element_states(project, expected))
    )
    laws = nc.element_residuals(law_project, flows, egl, states, model, nc.held_split_ks(expected))
    assert all(abs(r) <= tolerance for r in laws.heads.values()), laws.heads
    assert all(abs(r) <= flow_tolerance for r in laws.flows.values()), laws.flows


@pytest.mark.parametrize(
    "path",
    [p for p in CASES if {"pumps", "valves", "reliefValves"} & set(read_case(p)["expected"])],
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
    # Two float64 solutions agree to the heads' round-off at best (nc.ROUND_OFF × the head, under
    # 1e-9 m up to 1.1e6 m of head: the bound changes only in round_off_large_heads).
    for key, h in expected["egl"].items():
        assert egl[key] == pytest.approx(h, abs=max(1.0e-9, nc.ROUND_OFF * abs(h))), key


def _has_components(path: Path) -> bool:
    return bool({"pumps", "valves"} & set(read_case(path)["expected"]))


def _has_assigned_flows(path: Path) -> bool:
    return any(c["type"] == "assigned_flow" for c in read_case(path)["project"]["components"])


def _has_orifices(path: Path) -> bool:
    return any(c["type"] == "orifice" for c in read_case(path)["project"]["components"])


def _has_relief_valves(path: Path) -> bool:
    return any(c["type"] == "relief_valve" for c in read_case(path)["project"]["components"])


def _heads_pinned(path: Path) -> bool:
    """No pump, valve, assigned flow, orifice plate or relief valve: every head lies between
    reservoirs' fixed heads, and every element carries EPANET's g bias alike. An orifice plate
    or a relief valve is an EPANET GPV, a head-loss curve of the element's own law that carries
    no g bias while the pipes beside it do, so the heads between the reservoirs move by more
    (measured: up to 1.6 mm)."""
    return not (
        _has_components(path)
        or _has_assigned_flows(path)
        or _has_orifices(path)
        or _has_relief_valves(path)
    )


EPANET_CASES = [p for p in CASES if p.stem.startswith("epanet")]


@pytest.mark.parametrize(
    "path", [p for p in EPANET_CASES if _heads_pinned(p)], ids=lambda p: p.stem
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
    "path", [p for p in EPANET_CASES if not _heads_pinned(p)], ids=lambda p: p.stem
)
def test_epanet_component_case_agrees_with_our_model_inside_half_the_criterion(
    path: Path,
) -> None:
    """Pump, control-valve, demand and orifice networks: heads next to a pump or a fixed-flow
    valve, or along a path whose flow an assigned demand fixes, are not pinned by reservoirs, so
    EPANET's g = 32.2 ft/s² (0.08 % in every head loss) moves them by a few mm (measured: up to
    1.9 mm at the pump, 6.9 mm at the FCV, 7.1 mm at a demand of the gravity network and 16.4 mm
    at the far demand of the pumped one, 0.08 % of the 20 m lost on its way); an orifice plate's
    GPV curve carries no g bias, so the pipes' bias is not balanced across it (measured: flows
    within 3.2e-4, heads within 1.6 mm, in the loop's legs). Our model still lands
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


# --- Flow-controlled pumps (CLAUDE.md D11) ------------------------------------------------------


def _controlled_pumps(project: Project) -> list[Pump]:
    return [c for c in project.components if isinstance(c, Pump) and c.control is not None]


CONTROLLED_CASES = [p for p in CASES if _controlled_pumps(_load(p)[1])]


def test_controlled_pump_cases_exist() -> None:
    assert len(CONTROLLED_CASES) >= 20


@pytest.mark.parametrize("path", CONTROLLED_CASES, ids=lambda p: p.stem)
def test_controlled_pump_speed_and_state_are_consistent(path: Path) -> None:
    """Every flow-controlled pump has a control state and a speed (proposal vfd-pump-modes.md
    §2.4, §4.7): its status follows the state; a limit state runs at its limit speed; an
    active pump carries Q_set at a speed inside [s_lo, s_max] ⊆ [s_min, s_max], the stretch
    where F(·, Q_set) rises (§4.3, ``element_laws.stable_min_speed``); and a running pump's
    speed gives its expected head, F(s, Q) = s² H₀(Q/s) = EGL_d − EGL_s, which is also its
    operatingHead."""
    case, project = _load(path)
    expected = case["expected"]
    epanet = _is_epanet(case)
    for pump in _controlled_pumps(project):
        assert pump.control is not None
        want = expected["pumps"][pump.id]
        state, speed = want["controlState"], want["speed"]
        assert want["status"] == el.CONTROL_STATUS[state], pump.id
        limit = el.control_state_speed(pump.control, pump.speed, state)
        if limit is not None:
            assert speed == limit, pump.id
        else:
            curve = next(c for c in project.pump_library if c.id == pump.curve_id)
            s_lo = el.stable_min_speed(curve, pump.control, pump.speed)
            assert pump.control.min_speed <= s_lo <= speed <= pump.speed, pump.id
        q = nc.port_inflow(project, f"{pump.id}:suction", expected["flows"])
        assert want["operatingFlow"] == q, pump.id
        if want["status"] != "running":
            continue
        egl = expected["egl"]
        lift = egl[f"{pump.id}:discharge"] - egl[f"{pump.id}:suction"]
        if state == "active":
            # EPANET: float32 flows, and the FAQ substitute's closed pump passes Δh/CBIG.
            allowed = (
                8 * FLOAT32_REL * pump.control.setpoint + nc.EPANET_FCV_LEAK * abs(lift)
                if epanet
                else 0.0
            )
            assert abs(q - pump.control.setpoint) <= allowed, pump.id
        assert want["operatingHead"] == pytest.approx(lift, rel=1.0e-14, abs=1.0e-12), pump.id
        curve = next(c for c in project.pump_library if c.id == pump.curve_id)
        tolerance = 8 * FLOAT32_REL * max(abs(h) for h in egl.values()) if epanet else 1.0e-9
        assert abs(el.pump_head(curve, speed, q) - lift) <= tolerance, pump.id


@pytest.mark.parametrize(
    "path", [p for p in CONTROLLED_CASES if not p.stem.startswith("epanet")], ids=lambda p: p.stem
)
def test_controlled_pump_case_is_the_fixed_pump_at_its_speed(path: Path) -> None:
    """A second route to the flows (proposal §7.3, M1/M2): with every flow-controlled pump
    replaced by a fixed-speed pump at its expected speed, the whole-network solve (fsolve from
    a perturbed start, pumps by their head law) reproduces every expected flow and EGL, so an
    active pump's speed delivers exactly its setpoint."""
    case, project = _load(path)
    expected = case["expected"]
    fixed, states = nc.at_expected_speeds(project, expected)
    guess_q = {k: 1.2 * q + 1.0e-4 for k, q in expected["flows"].items()}
    guess_h = {k: h + 0.3 for k, h in expected["egl"].items()}
    flows, egl = nc.solve_network(fixed, nc.our_model(fixed), guess_q, guess_h, states)
    for key, q in expected["flows"].items():
        assert flows[key] == pytest.approx(q, rel=1.0e-9, abs=1.0e-15), key
    for key, h in expected["egl"].items():
        assert egl[key] == pytest.approx(h, abs=1.0e-9), key


@pytest.mark.parametrize(
    "curve_name",
    ["curve_straight", "curve_drooping", "curve_steep_rise"],
)
def test_psi_minimum_is_exact_against_dense_sampling(curve_name: str) -> None:
    """``psi_minimum`` (exact, from the PCHIP's cubic pieces) against ψ = 2H₀ − x H₀' sampled
    densely, inside the points and on the linear extension beyond them."""
    from tests.reference import derivations_pump_control as dpc
    from tests.reference.derivations_pumps import curve_a, curve_b, curve_c

    curves = [getattr(dpc, curve_name)(), curve_a(), curve_b(), curve_c()]
    for curve in curves:
        x_end = 2.0 * curve.points[-1].flow
        exact = dpc.psi_minimum(curve, 0.0, x_end)
        sampled = min(dpc.psi(curve, float(x)) for x in np.linspace(0.0, x_end, 20001))
        assert exact <= sampled + 1.0e-9
        assert exact == pytest.approx(sampled, abs=1.0e-3)


def test_stable_min_speed_is_capped_at_the_maximum_speed() -> None:
    """s_lo = max(s_min, Q_set/x_mono), at most s_max (proposal §4.3). The straight curve
    H₀ = 40 − 400 x has ψ = 2H₀ − x H₀' = 80 − 400 x, so x_mono = 0.2 m³/s. Q_set = 0.01 at
    s_min = 0.1: Q_set/s_min = 0.1 is within x_mono, s_lo = s_min. Q_set = 0.05: s_lo =
    Q_set/x_mono = 0.25. Q_set = 0.3: Q_set/s_max is beyond x_mono at s_max = 1 (and 0.8), so
    F(·, Q_set) falls on the whole range and s_lo = s_max; the active state then has no head
    band, so a lift between F(s_max, Q_set) and F(1.5, Q_set) (the uncapped Q_set/x_mono) is
    not an active state: F(1, 0.3) = 40 − 120 = −80 m, F(1.5, 0.3) = 2.25 (40 − 80) = −90 m."""
    from tests.reference import derivations_pump_control as dpc

    curve = dpc.curve_straight()
    assert el.x_mono(curve) == pytest.approx(0.2, rel=1.0e-12)

    def control(q_set: float) -> PumpControl:
        return PumpControl(mode="flow", setpoint=q_set, min_speed=0.1)

    assert el.stable_min_speed(curve, control(0.01), 1.0) == 0.1
    assert el.stable_min_speed(curve, control(0.05), 1.0) == pytest.approx(0.25, rel=1.0e-12)
    assert el.stable_min_speed(curve, control(0.3), 1.0) == 1.0
    assert el.stable_min_speed(curve, control(0.3), 0.8) == 0.8
    assert el.pump_head(curve, 1.0, 0.3) == pytest.approx(-80.0, rel=1.0e-12)
    assert el.pump_head(curve, 1.5, 0.3) == pytest.approx(-90.0, rel=1.0e-12)
    problem = el.controlled_pump_state_problem(
        "on", curve, control(0.3), 1.0, "active", 0.3, -85.0, -el.HTOL
    )
    assert problem is not None


def test_drooping_and_steep_curves_have_the_intended_psi() -> None:
    """CF18's two curves: the drooping one keeps ψ > 0 on its points (accepted, unique
    speed), the steep one has ψ ≤ 0 inside its points (CONTROLLED_PUMP_CURVE, proposal §4.3)."""
    from tests.reference import derivations_pump_control as dpc

    for name in ("curve_drooping", "curve_steep_rise"):
        curve = getattr(dpc, name)()
        heads = [p.head for p in curve.points]
        assert max(heads) > heads[0]  # both rise from shutoff before falling
    assert dpc.psi_minimum(dpc.curve_drooping(), 0.0, dpc.curve_drooping().points[-1].flow) > 0.0
    steep = dpc.curve_steep_rise()
    assert dpc.psi_minimum(steep, 0.0, steep.points[-1].flow) <= 0.0


# --- Equipment (docs/proposals/equipment-pressure-drop.md) ---------------------------------------


def _equipment_cases() -> list[Path]:
    return [
        p
        for p in CASES
        if any(c["type"] == "equipment" for c in read_case(p)["project"]["components"])
    ]


EQUIPMENT_CASES = _equipment_cases()


def test_equipment_cases_exist() -> None:
    """§7.1's closed-form cases (with the density-scaling row as two networks and decision 9's
    laminar case) and §7.2's three EPANET cases."""
    assert len(EQUIPMENT_CASES) == 15
    assert len([p for p in EQUIPMENT_CASES if p.stem.startswith("epanet")]) == 3


@pytest.mark.parametrize("d", [0.0127, 0.0525, 0.1023, 0.3048, 1.0, 2.5])
def test_equipment_coefficient_is_its_k_on_every_bore(d: float) -> None:
    """c = K/(2gA²) does not depend on the bore (K ∝ A², proposal §3.1): the K route and the
    rated-point definition agree to round-off for a rated point, a Cv and a Kv."""
    from tests.reference.case_format import rated_coefficient, rated_point

    for rating in (
        rated_point(50_000.0, 0.015, 999.1026214671009),
        rated_coefficient("Cv", 90.0),
        rated_coefficient("Kv", 60.0),
        rated_coefficient("Cv", 1.0e-3),
        rated_coefficient("Kv", 1.0e7),
    ):
        via_k = el.equipment_k(rating, d) / (2.0 * dv.G * dv.area(d) ** 2)
        assert via_k == pytest.approx(el.equipment_coefficient(rating), rel=2.0e-15), rating


@pytest.mark.parametrize("value", [1.0e-3, 0.5, 60.0, 90.0, 1.0e4, 1.0e7])
def test_equipment_cv_kv_agree_with_fluids_and_the_constants(value: float) -> None:
    """A Cv or Kv rating is a rated point on water (proposal §3.1): the suite's c (CoolProp's
    IAPWS-95 water at 60 °F, 703572 Pa) against fluids.fittings.Cv_to_K / Kv_to_K (the solver's
    conversion) on a 1 m bore, which differ by 3.1e-10 (fluids' water 101.25π² kg/m³ against
    CoolProp's); and the closed forms c·Kv² = 1.28e10/(π² g) (fluids) and c·Cv² =
    (1 psi)/(ρ_w g (1 US gpm)²) (the definition)."""
    from tests.reference.case_format import rated_coefficient

    for kind, convert in (("Cv", fluids.fittings.Cv_to_K), ("Kv", fluids.fittings.Kv_to_K)):
        rating = rated_coefficient(kind, value)  # type: ignore[arg-type]
        ours = el.equipment_coefficient(rating)
        theirs = float(convert(value, 1.0)) / (2.0 * dv.G * dv.area(1.0) ** 2)
        assert ours == pytest.approx(theirs, rel=3.2e-10), kind
        assert abs(ours / theirs - 1.0) > 2.0e-10, "the suite's water is its own, not fluids'"
    kv = el.equipment_coefficient(rated_coefficient("Kv", value)) * value**2
    assert kv == pytest.approx(1.28e10 / (math.pi**2 * dv.G), rel=3.2e-10)
    cv = el.equipment_coefficient(rated_coefficient("Cv", value)) * value**2
    definition = el.CV_PRESSURE_DROP / (el.REFERENCE_WATER_DENSITY * dv.G * el.CV_FLOW**2)
    assert cv == pytest.approx(definition, rel=1.0e-15)


@pytest.mark.parametrize("path", EQUIPMENT_CASES, ids=lambda p: p.stem)
def test_equipment_results_follow_their_definitions(path: Path) -> None:
    """Each expected equipment result (proposal §2.2) from the case's own expected flows, EGLs
    and pressures: the flow into the inlet port, Q/Q_r (None for a Cv or Kv), EGL_in − EGL_out,
    ρ g times it, and the static drop p_in − p_out equal to the §3.3 identity ρgh +
    ρg(z_out − z_in) + ρ(v_out² − v_in²)/2 with v in each port's pipe."""
    from opensolve_pipe.models.components import Equipment, RatedPoint

    case, project = _load(path)
    expected = case["expected"]
    rho = nc.density(project)
    elements = [c for c in project.components if isinstance(c, Equipment)]
    assert set(expected["equipment"]) == {e.id for e in elements}
    for e in elements:
        want = expected["equipment"][e.id]
        key_in, key_out = f"{e.id}:inlet", f"{e.id}:outlet"
        q = nc.port_inflow(project, key_in, expected["flows"])
        assert want["flow"] == q
        if isinstance(e.rating, RatedPoint):
            assert want["flowRatio"] == pytest.approx(q / e.rating.flow, rel=1.0e-15)
        else:
            assert want["flowRatio"] is None
        h = expected["egl"][key_in] - expected["egl"][key_out]
        assert want["headLoss"] == pytest.approx(h, rel=1.0e-15)
        assert want["pressureLoss"] == pytest.approx(rho * dv.G * h, rel=1.0e-15)
        p_in, p_out = expected["pressures"][key_in], expected["pressures"][key_out]
        assert want["pressureDrop"] == pytest.approx(p_in - p_out, rel=1.0e-12, abs=1.0e-9)
        v_in = nc.end_velocity(project, key_in, expected["flows"])
        v_out = nc.end_velocity(project, key_out, expected["flows"])
        z_in, z_out = nc.port_elevation(project, key_in), nc.port_elevation(project, key_out)
        identity = rho * dv.G * h + rho * dv.G * (z_out - z_in) + rho * (v_out**2 - v_in**2) / 2.0
        assert want["pressureDrop"] == pytest.approx(identity, rel=1.0e-12, abs=1.0e-9)


@pytest.mark.parametrize("path", EQUIPMENT_CASES, ids=lambda p: p.stem)
def test_equipment_flags_follow_reverse_and_laminar_flow(path: Path) -> None:
    """CORRELATION_OUT_OF_RANGE on an element exactly when its flow runs outlet → inlet or the
    lower Reynolds number of its two pipes' end segments is in (0, 2000) (proposal §3.2,
    decision 9); the cases include one of each kind and others with neither."""
    from opensolve_pipe.models.components import Equipment

    case, project = _load(path)
    expected = case["expected"]
    nu = nc.kinematic_viscosity(project)
    flagged = {
        f.get("componentId")
        for f in expected.get("flags", [])
        if f["code"] == "CORRELATION_OUT_OF_RANGE"
    }
    for e in (c for c in project.components if isinstance(c, Equipment)):
        q = expected["equipment"][e.id]["flow"]
        re = min(
            dv.reynolds(q, nc.port_diameter(project, f"{e.id}:{port}"), nu)
            for port in ("inlet", "outlet")
        )
        assert (e.id in flagged) == (q < 0.0 or 0.0 < re < dv.RE_LAMINAR), (e.id, q, re)


def test_equipment_flag_cases_cover_both_reasons() -> None:
    def flags(name: str) -> list[dict[str, str]]:
        flagged: list[dict[str, str]] = read_case(case_path(name))["expected"].get("flags", [])
        return flagged

    assert {"code": "CORRELATION_OUT_OF_RANGE", "componentId": "E1"} in flags(
        "equipment_reverse_flow"
    )
    assert {"code": "CORRELATION_OUT_OF_RANGE", "componentId": "E9"} in flags(
        "equipment_laminar_flag"
    )
    assert flags("equipment_line") == []


def test_equipment_rated_point_and_kv_definition_give_back_their_rating() -> None:
    """The solve gives back the datasheet (proposal §7.1): at the head difference built from it,
    a rated point passes Q_r with ΔP_r across (the case fluid is the rating fluid, ports level
    on equal bores), and Kv 60 passes 60 m³/h with 1 bar across (water at the reference
    density); a second route by the whole-network solve from a perturbed start."""
    for name, flow, drop in (
        ("equipment_rated_point", 0.015, 50_000.0),
        ("equipment_kv_definition", 60.0 / 3600.0, 1.0e5),
    ):
        case, project = _load(case_path(name))
        expected = case["expected"]
        flows, egl = nc.solve_network(
            project,
            nc.our_model(project),
            {k: 0.7 * q for k, q in expected["flows"].items()},
            {k: h - 0.5 for k, h in expected["egl"].items()},
            nc.element_states(project, expected),
        )
        assert flows["L1"] == pytest.approx(flow, rel=1.0e-12), name
        rho = nc.density(project)
        v = nc.end_velocity(project, "E1:inlet", flows)
        p_in = dv.static_pressure(rho, egl["E1:inlet"], nc.port_elevation(project, "E1:inlet"), v)
        p_out = dv.static_pressure(
            rho, egl["E1:outlet"], nc.port_elevation(project, "E1:outlet"), v
        )
        assert p_in - p_out == pytest.approx(drop, rel=1.0e-9), name
        assert expected["equipment"]["E1"]["pressureDrop"] == pytest.approx(drop, rel=1.0e-12)


def test_equipment_density_scaling_is_a_metamorphic_pair() -> None:
    """The line in a liquid 1.1 times as dense at the same ν (proposal §7.1 (a)): the same flows
    and EGLs as equipment_line, every static pressure and the loss × 1.1 (the head law has no
    density; ρ only converts head to pressure)."""
    base = read_case(case_path("equipment_line"))["expected"]
    dense = read_case(case_path("equipment_density_scaling"))["expected"]
    ratio = dense["fluid"]["density"] / base["fluid"]["density"]
    assert ratio == pytest.approx(1.1, rel=1.0e-15)
    for key, q in base["flows"].items():
        assert dense["flows"][key] == pytest.approx(q, rel=1.0e-12), key
    for key, h in base["egl"].items():
        assert dense["egl"][key] == pytest.approx(h, rel=1.0e-12, abs=1.0e-12), key
    for key, p in base["pressures"].items():
        assert dense["pressures"][key] == pytest.approx(ratio * p, rel=1.0e-11), key
    for field in ("pressureLoss", "pressureDrop"):
        assert dense["equipment"]["E1"][field] == pytest.approx(
            ratio * base["equipment"]["E1"][field], rel=1.0e-11
        )


def test_equipment_glycol_loss_is_the_density_scaled_rating() -> None:
    """In a fluid other than the rating's, the loss is the rating scaled with flow² and density
    (ISA-75.01.01 eq. (1)): ΔP_r (ρ/ρ_r)(Q/Q_r)² for E1's water rating in MEG, and
    (ρ/ρ_w) 1 psi (Q/Cv gpm)² for Cv 90 (ρ_w the reference water)."""
    from opensolve_pipe.models.components import Equipment, RatedPoint

    for name in ("equipment_density_scaling_glycol", "equipment_cv_glycol"):
        case, project = _load(case_path(name))
        rho = nc.density(project)
        [e] = [c for c in project.components if isinstance(c, Equipment)]
        q = case["expected"]["equipment"][e.id]["flow"]
        if isinstance(e.rating, RatedPoint):
            want = e.rating.pressure_loss * rho / e.rating.density * (q / e.rating.flow) ** 2
        else:
            q1 = e.rating.value * el.CV_FLOW
            want = rho / el.REFERENCE_WATER_DENSITY * el.CV_PRESSURE_DROP * (q / q1) ** 2
        got = case["expected"]["equipment"][e.id]["pressureLoss"]
        assert got == pytest.approx(want, rel=1.0e-12), name


def test_suction_strainer_lowers_npsh_available() -> None:
    """The strainer's loss lowers the suction EGL and so NPSHa (proposal §7.1): 4.0103 m with it
    against 5.1868 m on the same line without it (proposal: 5.186774563 m)."""
    from tests.reference import derivations_equipment as de

    with_strainer = read_case(case_path("equipment_suction_strainer_npsh"))["expected"]["pumps"]
    npsha = with_strainer["PU1"]["npshAvailable"]
    without = de.npsh_available_without_strainer()
    assert without == pytest.approx(5.186774563, rel=1.0e-9)
    assert npsha < without - 1.0


PROPOSAL_VALUES = {
    "equipment_line": ("flows", "L1", 0.0173994741),
    "equipment_density_scaling_glycol": ("flows", "L1", 0.0168778222),
    "equipment_ports_differ": ("flows", "L1", 0.0229019814),
    "equipment_in_loop": ("flows", "LA1", 0.0213608636),
    "equipment_assigned_demand": ("egl", "D:port_1", 16.978845625),
    "equipment_kv_definition": ("egl", "E1:inlet", 12.716016845),
    "equipment_cv_glycol": ("flows", "L1", 0.0170755360),
    "equipment_suction_strainer_npsh": ("flows", "L1", 0.0323599743),
}
"""A value of each case as the proposal's §7.1 table prints it, measured by its designers with
the element emulated as a valve: an independent route to each derivation. The Swamee–Jain cases
differ by 1.0-1.1e-7 (relative) on the single lines and, in the loop, by 1.8e-7 in the main,
1.2e-7 in leg A (LA1, the value checked here) and 2.8e-7 in the bypass leg LB, which the 2e-7
below would not pass and is not checked: the suite's Swamee–Jain is fluids' (6.97/Re)^0.9 form,
the solver's EPANET's 5.74/Re^0.9 (CLAUDE.md D7), 5.5e-6 apart in that term."""


@pytest.mark.parametrize("name", sorted(PROPOSAL_VALUES))
def test_equipment_derivations_reproduce_the_proposal(name: str) -> None:
    group, key, value = PROPOSAL_VALUES[name]
    got = read_case(case_path(name))["expected"][group][key]
    assert got == pytest.approx(value, rel=2.0e-7), (name, got, value)


# --- Orifice plates (docs/proposals/orifice-plate.md) ---------------------------------------------


def _plates(project: Project) -> list[Orifice]:
    return [c for c in project.components if isinstance(c, Orifice)]


ORIFICE_CASES = [p for p in CASES if _has_orifices(p)]
ORIFICE_TAPS: tuple[OrificeTaps, ...] = ("corner", "flange", "d_and_d_2")
FLUIDS_TAPS = {"corner": "corner", "flange": "flange", "d_and_d_2": "D"}
"""The fluids ``taps`` argument of each tap set."""


def test_orifice_cases_exist() -> None:
    """§7.1's twelve closed-form cases, the two added in review (C13 a moved entered C below its
    flange taps' Reynolds number, C14 reverse flow with the ports at different elevations) and
    §7.2's three EPANET cases."""
    assert len(ORIFICE_CASES) == 17
    assert len([p for p in ORIFICE_CASES if p.stem.startswith("epanet")]) == 3


@pytest.mark.parametrize("taps", ORIFICE_TAPS)
def test_rhg_transcription_equals_fluids(taps: OrificeTaps) -> None:
    """``element_laws.rhg_terms`` (ISO 5167-2:2003 eq. (4), transcribed from the fluids
    docstring) against fluids.flow_meter.C_Reader_Harris_Gallagher, the one implementation
    (D8/D9), at Re_D ≥ 5000 where fluids' two terms that are not ISO's never act, over D 20 mm
    to 1 m (the small-pipe term below 71.12 mm included) and β 0.1-0.75 (the proposal measured
    4.4e-16)."""
    import fluids.flow_meter

    mu, rho = 1.0e-3, 998.0
    for d_pipe in (0.0204, 0.0409, 0.0525, 0.0711, 0.1023, 0.3, 1.0):
        for beta in (0.1, 0.25, 0.4, 0.5, 0.56, 0.6, 0.7, 0.75):
            d = beta * d_pipe
            for re in (5000.0, 1.2e4, 1.0e5, 1.0e6, 1.0e8):
                m = math.pi * d_pipe * mu / 4.0 * re
                theirs = fluids.flow_meter.C_Reader_Harris_Gallagher(
                    d_pipe, d, rho, mu, m, FLUIDS_TAPS[taps]
                )
                assert el.orifice_c(d_pipe, d, re, taps) == pytest.approx(theirs, rel=1.0e-13)


def test_orifice_functions_reproduce_the_fluids_docstring_examples() -> None:
    """fluids 1.3.1's docstring examples of C_Reader_Harris_Gallagher, discharge_coefficient_to_K,
    K_to_discharge_coefficient and dP_orifice, through the suite's transcription."""
    rho, mu, m, d_pipe, d = 1.165, 1.85e-5, 0.12, 0.07391, 0.0222
    re = 4.0 * m / (math.pi * d_pipe * mu)
    assert rho > 0.0
    assert el.orifice_c(d_pipe, d, re, "flange") == pytest.approx(0.5990326277163659, rel=1e-13)
    assert el.orifice_k(0.07366, 0.05, 0.61512) == pytest.approx(5.2314291729754, rel=1.0e-12)
    assert el.orifice_c_from_k(0.07366, 0.05, 5.2314291729754) == pytest.approx(
        0.6151200000000001, rel=1.0e-12
    )
    # dP_orifice: the permanent loss K ρv²/2 at the flow eq. (1) gives for P1 − P2 = 17 kPa.
    beta = 0.05 / 0.07366
    c = 0.61512
    loss = el.orifice_k(0.07366, 0.05, c) * c * c * beta**4 / (1.0 - beta**4) * 17000.0
    assert loss == pytest.approx(9069.474705745388, rel=1.0e-12)


@pytest.mark.parametrize("c", [0.3, 0.5, 0.6, 0.8, 1.0])
def test_orifice_k_is_the_pressure_loss_relation(c: float) -> None:
    """K ρv²/2 = ISO 5167-2's pressure-loss relation [S − Cβ²]/[S + Cβ²] Δp, Δp from eq. (1)
    (fluids.flow_meter.dP_orifice); the cancellation-free K equals fluids'
    discharge_coefficient_to_K for β 0.02-0.97; the C ↔ K round trip (``orifice_c_from_k``,
    fluids' K_to_discharge_coefficient)."""
    import fluids.flow_meter as fm

    d_pipe = 0.1023
    for beta in np.linspace(0.02, 0.97, 96):
        d = float(beta) * d_pipe
        k = el.orifice_k(d_pipe, d, c)
        assert k == pytest.approx(fm.discharge_coefficient_to_K(d_pipe, d, c), rel=1.0e-12)
        assert el.orifice_c_from_k(d_pipe, d, k) == pytest.approx(c, rel=1.0e-12)
        assert fm.K_to_discharge_coefficient(d_pipe, d, k) == pytest.approx(c, rel=1.0e-12)
        b4 = (d / d_pipe) ** 4
        dp = 1.0e5  # Pa between the taps; eq. (1) gives ρv²/2 = Δp C²β⁴/(1 − β⁴)
        dynamic = dp * c * c * b4 / (1.0 - b4)
        loss = fm.dP_orifice(d_pipe, d, 2.0e5, 2.0e5 - dp, c)
        assert k * dynamic == pytest.approx(loss, rel=1.0e-11)


def test_orifice_k_at_c_one_is_borda_carnot() -> None:
    """At C = 1 (μ = 1, a jet the size of the bore) the relation is Borda–Carnot's sudden
    expansion from the bore, (1/β² − 1)² on the pipe's velocity, which is fluids'
    diffuser_sharp (on the bore's velocity) times (D/d)⁴ (decision 17)."""
    d_pipe = 0.1023
    for beta in (0.1, 0.3, 0.5, 0.7, 0.9):
        d = beta * d_pipe
        k = el.orifice_k(d_pipe, d, 1.0)
        assert k == pytest.approx(el.borda_carnot_k(d_pipe, d), rel=1.0e-12)
        sharp = fluids.fittings.diffuser_sharp(Di1=d, Di2=d_pipe) * (d_pipe / d) ** 4
        assert k == pytest.approx(sharp, rel=1.0e-12)


def test_orifice_pressure_loss_ratio_of_skelton() -> None:
    """Skelton et al. (28th NSFMW 2010): at β 0.4 and C 0.602 the pressure-loss ratio
    Δϖ/Δp = K C² β⁴/(1 − β⁴) is 0.823 (fluids gives 0.82296)."""
    ratio = el.orifice_k(1.0, 0.4, 0.602) * 0.602**2 * 0.4**4 / (1.0 - 0.4**4)
    assert ratio == pytest.approx(0.82296, abs=5.0e-6)
    assert round(ratio, 3) == 0.823


def test_orifice_k_has_no_cancellation_as_beta_tends_to_one() -> None:
    """K = u², u = (1 − β⁴)/(Cβ²(S + Cβ²)), 1 − β⁴ from (D − d)/D, stays positive and strictly
    decreasing in β down to 1 − β = 10⁻¹² and tends to its β → 1 limit ((1 − β⁴)/(2C²))² (S →
    C, so S + Cβ² → 2C) within 20(1 − β), relative (proposal decision 8, R5). fluids'
    subtractive form S/(Cβ²) − 1 keeps only about ε/(1 − β) of relative accuracy there (5e-5 at
    1 − β = 10⁻¹², C 0.6, measured), which this form does not lose."""
    d_pipe = 0.1023
    for c in (0.3, 0.6, 1.0):
        previous = math.inf
        for k in range(3, 13):
            d = d_pipe * (1.0 - 10.0**-k)
            value = el.orifice_k(d_pipe, d, c)
            assert 0.0 < value < previous
            limit = (el.one_minus_beta4(d_pipe, d) / (2.0 * c * c)) ** 2
            assert value == pytest.approx(limit, rel=20.0 * 10.0**-k)
            previous = value


def test_orifice_hold_and_re_lo() -> None:
    """Re_lo = max(5000, 16000β²) (corner, D and D/2) and max(5000, 170000β²D) (flange), made
    continuous at β 0.56 (decision 7: 5017.6 there); below it C is held, so K is constant there
    and continuous at Re_lo; the held K strictly decreases in β across 0.56 (R4)."""
    assert el.orifice_re_lo("d_and_d_2", 0.56, 0.1) == pytest.approx(5017.6, rel=1e-12)
    assert el.orifice_re_lo("corner", 0.5, 0.1) == 5000.0
    flange = el.orifice_re_lo("flange", 0.75, 0.3)
    assert flange == pytest.approx(170000 * 0.5625 * 0.3, rel=1e-15)
    law = el.OrificeLaw(0.1023, 0.05115, 998.0, 1.0e-3)
    q_lo = law.re_lo_loss * math.pi * 0.1023 * 1.0e-3 / (4.0 * 998.0)
    assert law.k(1.0e-9) == law.k(0.5 * q_lo)
    assert law.k(q_lo * (1.0 + 1.0e-9)) == pytest.approx(law.k(0.5 * q_lo), rel=1.0e-8)
    held = [
        el.OrificeLaw(0.1023, float(b) * 0.1023, 998.0, 1.0e-3).k(1.0e-9)
        for b in np.linspace(0.5585, 0.5615, 3001)
    ]
    assert all(b < a for a, b in itertools.pairwise(held))


def test_orifice_head_increases_with_flow() -> None:
    """h(Q) strictly increases on every case's plates (over 10⁻⁷ to 10 times the case's flow),
    so each brentq root is the case's only flow (proposal §3.1)."""
    for path in ORIFICE_CASES:
        case, project = _load(path)
        rho, mu, _ = nc.fluid_state(project)
        for o in _plates(project):
            law = el.orifice_law(o, nc.port_diameter(project, f"{o.id}:inlet"), rho, mu)
            q = abs(case["expected"]["orifices"][o.id]["flow"])
            heads = [law.head(float(x)) for x in np.geomspace(1.0e-7 * q, 10.0 * q, 400)]
            assert all(b > a for a, b in itertools.pairwise(heads)), (path.stem, o.id)


@pytest.mark.parametrize("path", ORIFICE_CASES, ids=lambda p: p.stem)
def test_orifice_results_follow_their_definitions(path: Path) -> None:
    """Each expected orifice result (proposal §2.2) from the case's own expected flows, EGLs and
    pressures and the plate's inputs: the flow into the inlet port, EGL_in − EGL_out, ρg times
    it, the static drop p_in − p_out equal to the §3.7 identity, β = d/D on the inlet pipe's
    bore, Re_D = 4ρ|Q|/(πDμ), K = K(C_L), the reading (1 − β⁴)/(C_M²β⁴) ρv|v|/2, and the vena
    contracta pressure of decision 15 from the expected port pressures; the echoed inputs."""
    case, project = _load(path)
    expected = case["expected"]
    rho, mu, _ = nc.fluid_state(project)
    plates = _plates(project)
    assert set(expected["orifices"]) == {o.id for o in plates}
    for o in plates:
        want = expected["orifices"][o.id]
        key_in, key_out = f"{o.id}:inlet", f"{o.id}:outlet"
        q = nc.port_inflow(project, key_in, expected["flows"])
        d_pipe = nc.port_diameter(project, key_in)
        assert want["flow"] == q
        assert want["pipeDiameter"] == d_pipe
        assert want["boreDiameter"] == o.bore_diameter
        assert want["taps"] == o.taps
        assert want["beta"] == pytest.approx(o.bore_diameter / d_pipe, rel=1.0e-15)
        h = expected["egl"][key_in] - expected["egl"][key_out]
        assert want["headLoss"] == pytest.approx(h, rel=1.0e-15)
        assert want["pressureLoss"] == pytest.approx(rho * dv.G * h, rel=1.0e-15)
        p_in, p_out = expected["pressures"][key_in], expected["pressures"][key_out]
        assert want["pressureDrop"] == pytest.approx(p_in - p_out, rel=1.0e-12, abs=1.0e-9)
        v_in = nc.end_velocity(project, key_in, expected["flows"])
        v_out = nc.end_velocity(project, key_out, expected["flows"])
        z_in, z_out = nc.port_elevation(project, key_in), nc.port_elevation(project, key_out)
        identity = rho * dv.G * h + rho * dv.G * (z_out - z_in) + rho * (v_out**2 - v_in**2) / 2.0
        assert want["pressureDrop"] == pytest.approx(identity, rel=1.0e-12, abs=1.0e-9)
        re = 4.0 * rho * abs(q) / (math.pi * d_pipe * mu)
        assert want["reynoldsNumber"] == pytest.approx(re, rel=1.0e-14)
        c_l = want["dischargeCoefficient"]
        k = el.orifice_k(d_pipe, o.bore_diameter, c_l)
        assert want["lossCoefficient"] == pytest.approx(k, rel=1.0e-14)
        b4 = (o.bore_diameter / d_pipe) ** 4
        c_m = want["meterDischargeCoefficient"]
        if o.taps is None:
            assert c_m is None
            assert want["differentialPressure"] is None
        else:
            reading = (1.0 - b4) / (c_m * c_m * b4) * rho * v_in * abs(v_in) / 2.0
            assert want["differentialPressure"] == pytest.approx(reading, rel=1.0e-12)
        up, down = ("inlet", "outlet") if q > 0.0 else ("outlet", "inlet")
        z = {"inlet": z_in, "outlet": z_out}
        jet = (1.0 - b4) / (c_l * c_l * b4) * rho * v_in**2 / 2.0
        vc = expected["pressures"][f"{o.id}:{up}"] + rho * dv.G * (z[up] - z[down]) - jet
        assert want["venaContractaPressure"] == pytest.approx(vc, rel=1.0e-12, abs=1.0e-7)


@pytest.mark.parametrize("path", ORIFICE_CASES, ids=lambda p: p.stem)
def test_orifice_coefficients_are_iso_5167_2s(path: Path) -> None:
    """C_L and C_M from their definitions (decisions 5, 7, 13, 14), written here once more from
    the inputs: ISO's C at D and D/2 at max(Re_D, max(5000, 16000β²)), or the entered C moved by
    eq. (4)'s ratio from corner or flange taps; C_M ISO's at the plate's taps held at their own
    Re_lo, or the entered C; with the source, the Re of eq. (4) and the ratio."""
    case, project = _load(path)
    expected = case["expected"]
    for o in _plates(project):
        want = expected["orifices"][o.id]
        d_pipe, d = want["pipeDiameter"], o.bore_diameter
        beta = d / d_pipe
        re = want["reynoldsNumber"]
        re_l = max(re, 5000.0, 16000.0 * beta * beta)
        iso_dd2 = el.orifice_c(d_pipe, d, re_l, "d_and_d_2")
        entered, taps = o.discharge_coefficient, o.taps
        if entered is None:
            assert want["coefficientSource"] == "iso_5167_2"
            assert want["dischargeCoefficient"] == pytest.approx(iso_dd2, rel=1.0e-14)
            assert want["coefficientReynoldsNumber"] == pytest.approx(re_l, rel=1.0e-15)
            assert want["tapCoefficientRatio"] is None
            if taps is None:
                assert want["meterDischargeCoefficient"] is None
            else:
                own = 170000.0 * beta * beta * d_pipe if taps == "flange" else 16000.0 * beta**2
                c_m = el.orifice_c(d_pipe, d, max(re, 5000.0, own), taps)
                assert want["meterDischargeCoefficient"] == pytest.approx(c_m, rel=1.0e-14)
        else:
            assert want["coefficientSource"] == "entered"
            assert want["meterDischargeCoefficient"] == (None if taps is None else entered)
            if taps in ("corner", "flange"):
                assert taps is not None
                r = iso_dd2 / el.orifice_c(d_pipe, d, re_l, taps)
                assert want["tapCoefficientRatio"] == pytest.approx(r, rel=1.0e-14)
                assert want["dischargeCoefficient"] == pytest.approx(entered * r, rel=1.0e-14)
                assert want["coefficientReynoldsNumber"] == pytest.approx(re_l, rel=1.0e-15)
            else:
                assert want["dischargeCoefficient"] == entered
                assert want["tapCoefficientRatio"] is None
                assert want["coefficientReynoldsNumber"] is None


@pytest.mark.parametrize("path", ORIFICE_CASES, ids=lambda p: p.stem)
def test_orifice_flags_follow_their_inequalities(path: Path) -> None:
    """The expected CORRELATION_OUT_OF_RANGE limits of each plate are exactly the inequalities
    §3.5 lists that its case breaks, and BELOW_VAPOR_PRESSURE on the plate exactly when its
    vena contracta's absolute pressure is below the vapor pressure (0 Pa without one)."""
    case, project = _load(path)
    expected = case["expected"]
    _, _, p_vap = nc.fluid_state(project)
    p_atm = dv.standard_atmosphere_pressure(project.settings.site_elevation)
    flags = expected.get("flags", [])
    for o in _plates(project):
        want = expected["orifices"][o.id]
        d_pipe, d, re = want["pipeDiameter"], o.bore_diameter, want["reynoldsNumber"]
        beta = d / d_pipe
        eq4 = o.discharge_coefficient is None or o.taps in ("corner", "flange")
        limits = set()
        if eq4 and d < 0.0125:
            limits.add("boreDiameter")
        if eq4 and not 0.05 <= d_pipe <= 1.0:
            limits.add("pipeDiameter")
        if eq4 and not 0.1 <= beta <= 0.75:
            limits.add("beta")
        lows = [max(5000.0, 16000.0 * beta * beta)]
        if eq4 and o.taps is not None:  # ISO's C_M, or a moved entered C's denominator
            lows.append(el.orifice_re_lo(o.taps, beta, d_pipe))
        if eq4 and any(re < low for low in lows):
            limits.add("reynoldsNumber")
        if nc.port_diameter(project, f"{o.id}:outlet") != d_pipe:
            limits.add("outletDiameter")
        if o.discharge_coefficient is not None and re < 2000.0:
            limits.add("laminar")
        if want["flow"] < 0.0:
            limits.add("reverseFlow")
        flagged = {
            f["limit"]
            for f in flags
            if f["code"] == "CORRELATION_OUT_OF_RANGE" and f.get("componentId") == o.id
        }
        assert flagged == limits, (o.id, flagged, limits)
        threshold = 0.0 if p_vap is None else p_vap
        flashing = want["venaContractaPressure"] + p_atm < threshold
        vena = {
            "code": "BELOW_VAPOR_PRESSURE",
            "componentId": o.id,
            "detail": "venaContractaAbsolutePressure",
        }
        assert (vena in flags) == flashing, o.id


def test_orifice_flag_cases_cover_the_limits() -> None:
    """The cases flag each kind §7.1 names (d, D, Re, the outlet bore, reverse flow, flashing at
    the vena contracta), and C1 flags nothing."""
    found = {
        f.get("limit") or f["code"]
        for p in ORIFICE_CASES
        for f in read_case(p)["expected"].get("flags", [])
    }
    assert {
        "boreDiameter",
        "pipeDiameter",
        "reynoldsNumber",
        "outletDiameter",
        "reverseFlow",
        "BELOW_VAPOR_PRESSURE",
    } <= found
    assert read_case(case_path("orifice_line"))["expected"].get("flags", []) == []


def test_orifice_line_flow_does_not_depend_on_the_taps() -> None:
    """One loss per plate (decision 5, owner's answer Q3): C1 with no taps, corner taps or D and
    D/2 taps has the same flow bit for bit; only the reading changes (proposal §7.1: 91,778.82
    Pa at corner and 91,981.18 Pa at D and D/2 tappings, 91,977.61225 Pa at flange)."""
    fluid = do.liquid_a()
    rho, mu, _ = dv.fluid_state(fluid)
    base = do.line_series()
    q = base.flow(rho, mu, "colebrook")
    readings: dict[OrificeTaps | None, float | None] = {}
    for taps in (None, "corner", "d_and_d_2", "flange"):
        series = do.with_taps(base, taps)
        assert series.flow(rho, mu, "colebrook") == q
        readings[taps] = series.law(rho, mu).differential(q)
    assert readings[None] is None
    assert readings["corner"] == pytest.approx(91778.82, abs=0.005)
    assert readings["d_and_d_2"] == pytest.approx(91981.18, abs=0.005)
    assert readings["flange"] == pytest.approx(91977.61225, abs=1.0e-5)


def test_orifice_meter_reading_reads_back_the_flow() -> None:
    """C2's reading at Q* = 12 L/s, put into fluids' differential_pressure_meter_solver (ISO
    5167 orifice, flange taps, ε = 1), gives back the mass flow ρQ* (proposal: −1.1e-16)."""
    import fluids.flow_meter as fm

    case, project = _load(case_path("orifice_meter_readback"))
    want = case["expected"]["orifices"]["OR1"]
    rho, mu, _ = nc.fluid_state(project)
    m = fm.differential_pressure_meter_solver(
        D=want["pipeDiameter"],
        rho=rho,
        mu=mu,
        D2=want["boreDiameter"],
        P1=2.0e5,
        P2=2.0e5 - want["differentialPressure"],
        meter_type="ISO 5167 orifice",
        taps="flange",
        epsilon_specified=1.0,
    )
    assert want["flow"] == do.METER_FLOW
    assert m == pytest.approx(rho * do.METER_FLOW, rel=1.0e-9)


@pytest.mark.parametrize(
    ("re", "move"), [(1.0e5, -1.216e-2), (1.0e6, -1.650e-2), (1.0e8, -1.907e-2)]
)
def test_a_c_held_at_another_reynolds_number_misses_c7_beyond_d6(re: float, move: float) -> None:
    """C7 (Re_D ≈ 12,400): ISO's C held at Re 10⁵, 10⁶ or 10⁸ moves the flow by −1.216, −1.650
    or −1.907 % (proposal §7.1), beyond D6's 0.5 %: the case tells a wrong Re dependence apart."""
    name, rho, mu = do.LIGHT_OIL
    q = read_case(case_path("orifice_reynolds_dependence"))["expected"]["flows"]["L1"]
    held = do.held_c_flow(do.re_dependence_series(), custom_fluid(name, rho, mu), re)
    assert held / q - 1.0 == pytest.approx(move, abs=5.0e-6)
    assert abs(held / q - 1.0) > 0.005


def test_c12_entered_c_moved_and_on_iso_c() -> None:
    """C12: 0.6 used for the loss as entered would move the flow by −2.519 %, beyond D6 (the
    move matters); on ISO's C the same network passes 0.02134831923356 m³/s with C_L
    0.6134828942 and C_M 0.6008290351755132 (proposal §7.1), and an entered C equal to that
    C_M gives ISO's flow (the calibration identity in closed form, decision 13)."""
    rho, mu, _ = dv.fluid_state(do.liquid_a())
    q = read_case(case_path("orifice_entered_c_at_taps"))["expected"]["flows"]["L1"]
    as_entered = do.with_taps(do.corner_series(), None)
    assert as_entered.flow(rho, mu, "colebrook") / q - 1.0 == pytest.approx(-2.519e-2, abs=5e-6)
    iso = do.corner_series(entered=None)
    q_iso = iso.flow(rho, mu, "colebrook")
    assert q_iso == pytest.approx(0.02134831923356, rel=1.0e-11)
    law = iso.law(rho, mu)
    assert law.c_loss(q_iso) == pytest.approx(0.6134828942, rel=1.0e-9)
    c_m = law.c_meter(q_iso)
    assert c_m == pytest.approx(0.6008290351755132, rel=1.0e-12)
    calibrated = do.corner_series(entered=c_m)
    assert calibrated.flow(rho, mu, "colebrook") == pytest.approx(q_iso, rel=1.0e-13)


def test_epanet_orifice_cases_agree_with_the_closed_form() -> None:
    """EPANET's GPV runs (proposal §7.2) against the closed form of the same networks in EPANET
    water with the suite's Swamee–Jain (the proposal's references: Q 0.01740061988423;
    Q_A 0.01016327504258, Q_B 0.01332101666158; Q 5.966495101066e-4): within 3.5e-4 in flow
    (EPANET's g in the pipes, the interpolated curve); on E3, a C held at Re 10⁸ would miss by
    9.2e-3, beyond D6, so EPANET tells the Reynolds-number dependence apart there. The closed
    forms differ from the proposal's prints by up to 2.1e-7 (Q_B): the suite's Swamee–Jain is
    fluids' (6.97/Re)^0.9 form, the proposal's EPANET's 5.74/Re^0.9 (CLAUDE.md D7), as for the
    equipment loop (``PROPOSAL_VALUES``)."""
    fluid = do.epanet_water()
    rho, mu, _ = dv.fluid_state(fluid)
    e1 = read_case(case_path("epanet_orifice_line"))["expected"]["flows"]["L1"]
    q1 = do.line_series().flow(rho, mu, "swamee_jain")
    assert q1 == pytest.approx(0.01740061988423, rel=5.0e-7)
    assert abs(e1 / q1 - 1.0) < 3.5e-4
    _, loop = _load(case_path("epanet_orifice_balancing"))
    sol = do.solve_loop(loop, "swamee_jain")
    flows = read_case(case_path("epanet_orifice_balancing"))["expected"]["flows"]
    assert sol.q_a == pytest.approx(0.01016327504258, rel=5.0e-7)
    assert sol.q_b == pytest.approx(0.01332101666158, rel=5.0e-7)
    assert abs(flows["LA1"] / sol.q_a - 1.0) < 3.5e-4
    assert abs(flows["LB1"] / sol.q_b - 1.0) < 3.5e-4
    _, low = _load(case_path("epanet_orifice_low_re"))
    e3 = read_case(case_path("epanet_orifice_low_re"))["expected"]["flows"]["L1"]
    [plate] = _plates(low)
    series = do.Series(0.0, 1.2, 0.0, 0.0, *do.LOW_RE_LINES, plate)
    q3 = series.flow(rho, mu, "swamee_jain")
    assert q3 == pytest.approx(5.966495101066e-4, rel=5.0e-7)
    assert abs(e3 / q3 - 1.0) < 3.0e-5
    held = do.held_c_flow(series, fluid, 1.0e8)
    assert held / q3 - 1.0 == pytest.approx(-9.2e-3, abs=1.0e-4)
    assert abs(held / e3 - 1.0) > 0.005


ORIFICE_PROPOSAL_VALUES: dict[str, list[tuple[str, str, float]]] = {
    "orifice_line": [
        ("flows", "L1", 0.01742501098029),
        ("orifices.OR1", "pressureLoss", 67393.32279),
        ("orifices.OR1", "venaContractaPressure", -30298.95924),
    ],
    "orifice_meter_readback": [("orifices.OR1", "differentialPressure", 43531.76776)],
    "orifice_entered_c": [("flows", "L1", 0.01732389858578)],
    "orifice_reverse_flow": [("orifices.OR1", "venaContractaPressure", -22246.14305)],
    "orifice_outside_iso_geometry": [("orifices.OR1", "differentialPressure", 306609.9411)],
    "orifice_low_reynolds": [("flows", "L1", 0.005451562364008)],
    "orifice_reynolds_dependence": [("flows", "L1", 0.01373313452249)],
    "orifice_balancing_loop": [
        ("flows", "LA1", 0.01017566844332),
        ("egl", "T2:run_inlet", 2.747714002),
    ],
    "orifice_min_flow_bypass": [
        ("egl", "T1:branch", 28.61046775),
        ("flows", "LB1", 0.002543446580695),
    ],
    "orifice_vena_contracta_flashing": [("orifices.RO", "pressureLoss", 1798635.117)],
    "orifice_outlet_bore_differs": [("orifices.OR1", "pressureDrop", 75558.76276)],
    "orifice_entered_c_at_taps": [
        ("flows", "L1", 0.02131227740861),
        ("orifices.OR1", "tapCoefficientRatio", 1.021059944023),
    ],
}
"""Values of each case as the proposal's §7.1 table prints them, measured by its designers with
the plate emulated in the real solver as a gate valve of K = K(Q*): an independent route to each
derivation (the prints have 10-13 significant digits)."""


@pytest.mark.parametrize("name", sorted(ORIFICE_PROPOSAL_VALUES))
def test_orifice_derivations_reproduce_the_proposal(name: str) -> None:
    expected = read_case(case_path(name))["expected"]
    for group, key, value in ORIFICE_PROPOSAL_VALUES[name]:
        where: Any = expected
        for part in group.split("."):
            where = where[part]
        assert where[key] == pytest.approx(value, rel=1.0e-9), (name, group, key)


# --- Pressure relief valves (docs/proposals/pressure-relief-valve.md) -----------------------------


def _relief_valves(project: Project) -> list[ReliefValve]:
    return [c for c in project.components if isinstance(c, ReliefValve)]


RELIEF_CASES = [p for p in CASES if _has_relief_valves(p)]


def test_relief_cases_exist() -> None:
    """§7.1's C1-C15 (C9 and C11 two cases each, C16 in test_floating_sections), the closed-off
    valve, and §7.2's three EPANET cases."""
    assert len(RELIEF_CASES) == 21
    assert len([p for p in RELIEF_CASES if p.stem.startswith("epanet")]) == 3


def _cubic_root_60_digits(dp_s: float, r: float, q: float) -> decimal.Decimal:
    """The largest real root of u³ − Δp_s u − R q = 0 by Newton's method in 60-digit decimal
    arithmetic from above (the cubic is increasing and convex beyond its largest root, so the
    iterates fall monotonically onto it), with Δp_s, R and q the doubles given, exactly."""
    context = decimal.Context(prec=60)
    a, b = decimal.Decimal(dp_s), decimal.Decimal(r) * decimal.Decimal(q)
    u = context.sqrt(a) * 2 + context.power(b, decimal.Decimal(1) / 3) + 1
    for _ in range(500):
        f = context.subtract(context.subtract(context.power(u, 3), context.multiply(a, u)), b)
        df = context.subtract(context.multiply(3, context.power(u, 2)), a)
        step = context.divide(f, df)
        u = context.subtract(u, step)
        if abs(step) <= abs(u) * decimal.Decimal("1e-55"):
            return u
    raise RuntimeError("Newton did not converge")


RELIEF_LAW_GRID = [
    (rho, c_area, dp_s, op)
    for rho in (700.0, 998.0, 1300.0)
    for c_area in (1.0e-6, 1.2874e-4, 0.03)
    for dp_s in (1.0e4, 5.0e5, 3.0e7)
    for op in (1.0e-3, 0.1, 0.2, 1.0 / 3.0, 0.5, 1.0)
]
"""The proposal's S1b ranges (ρ 700-1300 kg/m³, C 10⁻⁶-0.03 m², Δp_s 10⁴-3×10⁷ Pa, op 10⁻³-1),
at op 1/3 the switch between the trigonometric and the hyperbolic forms (proposal §3.1, S1g)."""
FLOW_FRACTIONS = (1.0e-9, 1.0e-3, 0.1, 0.5, 0.9, 0.999999, 1.0)


@pytest.mark.parametrize(("rho", "c_area", "dp_s", "op"), RELIEF_LAW_GRID)
def test_relief_band_root_is_the_cubic_root(
    rho: float, c_area: float, dp_s: float, op: float
) -> None:
    """The suite's band root (Chebyshev's cos/cosh forms, ``element_laws.ReliefLaw.band_root``)
    against a 60-digit Newton solve of the cubic (within 4×10⁻¹⁵ relative, the proposal's S1b
    measured 8.2×10⁻¹⁶ for its own form), and the excess Δp_t − Δp_s = RQ/u, which avoids the
    cancellation of u² − Δp_s (decision 13), against the 60-digit u² − Δp_s (8×10⁻¹⁵). The
    forward law at the root, Q = x·C·√(2Δp_t/ρ) with x the clipped linear lift, gives the flow
    back to its own cancellation: (Δp_t − Δp_s) from the double Δp_t loses about ε·Δp_s/(Δp_t −
    Δp_s) relative (the round trip the proposal's S1a measured at 4.6×10⁻¹⁰)."""
    law = el.ReliefLaw(rho, c_area, 1.0, dp_s, op)
    for fraction in FLOW_FRACTIONS:
        q = fraction * law.q_full
        u = law.band_root(q)
        exact = _cubic_root_60_digits(dp_s, law.r, q)
        assert abs(decimal.Decimal(u) - exact) <= decimal.Decimal("4e-15") * exact, (fraction, u)
        exact_excess = exact * exact - decimal.Decimal(dp_s)
        excess = law.excess(q)
        # At Q_f itself the full-lift branch ρQ²/(2C²) − Δp_s holds the subtraction, a few ulps of
        # Δp_f (an absolute error far below any head the solver resolves).
        bound = 8.0e-15 if fraction < 1.0 else 8.0 * 2.0**-52 * law.full_lift_pressure / excess
        assert abs(decimal.Decimal(excess) - exact_excess) <= decimal.Decimal(bound) * exact_excess
        dp_t = law.total_pressure_difference(q)
        cancellation = 16.0 * 2.0**-52 * dp_s / excess
        assert law.flow_at(dp_t) == pytest.approx(q, rel=max(1.0e-12, cancellation), abs=0.0), (
            fraction
        )


@pytest.mark.parametrize("op", [1.0e-3, 0.1, 0.2, 0.5, 1.0])
def test_relief_law_is_continuous_at_full_lift_with_a_slope_step(op: float) -> None:
    """At Q_f the band's Δp_t meets API 520's ρQ²/(2C²) (continuous), and its slope steps up:
    from the left dΔp/dQ·C²/(ρQ_f) = op/(2 + 3op), the least band slope (proposal §3.1, S1d), from
    the right 1. h(Q) increases strictly across the band and beyond."""
    law = el.ReliefLaw(998.0, 1.9806412e-4, 0.65, 5.0e5, op)
    q_f = law.q_full
    assert law.excess(q_f * (1.0 - 1.0e-15)) == pytest.approx(law.excess(q_f), rel=1.0e-12)
    scale = 998.0 * q_f / law.c**2
    step = q_f * 1.0e-7
    left = (law.excess(q_f) - law.excess(q_f - step)) / step / scale
    right = (law.excess(q_f + step) - law.excess(q_f)) / step / scale
    assert left == pytest.approx(op / (2.0 + 3.0 * op), rel=1.0e-5)
    assert right == pytest.approx(1.0, rel=1.0e-5)
    heads = [law.head(q_f * i / 400.0) for i in range(601)]
    assert all(b > a for a, b in itertools.pairwise(heads))
    # The slope at 0+ is R/(√Δp_s ρg) (decision 12): finite and positive (read on the excess,
    # which holds no h_set to cancel).
    tiny = q_f * 1.0e-9
    slope0 = law.excess(tiny) / tiny / (998.0 * dv.G)
    assert slope0 == pytest.approx(law.r / (math.sqrt(5.0e5) * 998.0 * dv.G), rel=1.0e-6)


API520_ROUNDING = (
    11.78 / (math.sqrt(1.0e-3 * fluids.safety_valve.rho0) / 60000.0 * math.sqrt(2.0) / 2.0 * 1.0e6)
    - 1.0
)
"""API 520's 11.78 over the exact constant fluids documents, 11.779282389196 (its reference
water density ``rho0``): +6.0921436×10⁻⁵ (proposal decision 4, S1f)."""


@pytest.mark.parametrize("letter", list(fluids.safety_valve.API526_letters))
def test_relief_full_lift_is_api520_a_l(letter: str) -> None:
    """At full lift the law is API 520's liquid equation in exact SI (decision 4): fluids'
    ``API520_A_l`` at the mass flow ρQ_f and P1 − P2 = Δp_f, Kd 0.65, Kw = Kc = Kv = 1 (both
    passed: Kw None would apply the balanced-bellows table, proposal §3.10), gives the letter's
    effective area times 1 + 6.0921×10⁻⁵, the rounding of API's 11.78, for any fluid and back
    pressure."""
    assert pytest.approx(6.0921436e-5, abs=1.0e-12) == API520_ROUNDING
    area = el.API526_AREAS[letter]
    for rho, dp_s, back in ((998.0, 5.0e5, 101325.0), (1040.0, 2.0e6, 3.0e5)):
        law = el.ReliefLaw(rho, area, el.API520_EFFECTIVE_KD, dp_s, el.asme_overpressure(dp_s))
        required = fluids.safety_valve.API520_A_l(
            m=rho * law.q_full,
            rho=rho,
            P1=law.full_lift_pressure + back,
            P2=back,
            overpressure=law.overpressure,
            Kd=0.65,
            Kc=1.0,
            Kw=1.0,
            Kv=1.0,
        )
        assert required / area - 1.0 == pytest.approx(API520_ROUNDING, rel=1.0e-9)


def test_relief_effective_coefficient_and_areas_are_fluids() -> None:
    """API 520's effective Kd 0.65 is ``API520_A_l``'s default; API 526's areas are fluids'
    ``API526_A`` (the in² table × 0.0254²), D to T."""
    assert el.API520_EFFECTIVE_KD == 0.65
    assert list(el.API526_AREAS) == list(fluids.safety_valve.API526_letters)
    for (letter, area), sq_in in zip(
        el.API526_AREAS.items(), fluids.safety_valve.API526_A_sq_inch, strict=True
    ):
        assert area == pytest.approx(sq_in * inch**2, rel=1.0e-15), letter


@pytest.mark.parametrize("letter", list(fluids.safety_valve.API526_letters))
def test_relief_covering_letter_is_api520_round_size(letter: str) -> None:
    """The smallest API 526 letter whose effective area is at least an area (proposal §2.2) is
    the letter of fluids' ``API520_round_size``: at a letter's own area, just above it, and None
    above T's (where fluids raises)."""
    letters = list(fluids.safety_valve.API526_letters)
    area = el.API526_AREAS[letter]
    for a in (area, area * (1.0 - 1.0e-9), area * (1.0 + 1.0e-9)):
        try:
            rounded = fluids.safety_valve.API520_round_size(a)
        except ValueError:
            assert el.covering_letter(a) is None
            assert letter == "T"
            continue
        assert el.covering_letter(a) == letters[fluids.safety_valve.API526_A.index(rounded)]
    assert el.covering_letter(1.0e-9) == "D"


def test_relief_asme_default_overpressure() -> None:
    """ASME's default (decision 6): max(10 %, 3 psi/Δp_s), crossing at 3 psi/0.1 = 206,842.72 Pa,
    0.2 at the 15 psi scope (103,421.36 Pa), not defined below it."""
    crossover = el.ASME_OVERPRESSURE_FLOOR / el.ASME_OVERPRESSURE
    assert crossover == pytest.approx(206_842.72, abs=0.01)
    assert el.asme_overpressure(crossover * 1.001) == 0.1
    assert el.asme_overpressure(crossover * 0.999) == pytest.approx(0.1 / 0.999, rel=1.0e-12)
    assert pytest.approx(103_421.36, abs=0.01) == el.ASME_MINIMUM_SET
    assert el.asme_overpressure(el.ASME_MINIMUM_SET) == pytest.approx(0.2, rel=1.0e-15)
    with pytest.raises(ValueError, match="not cited below a 15 psi set"):
        el.asme_overpressure(el.ASME_MINIMUM_SET * (1.0 - 1.0e-12))


def test_published_relief_data_is_the_suites() -> None:
    """``x-relief-data`` (decision 27) holds what the suite derives on its own: fluids' API 526
    areas, API520_A_l's Kd, 10 %, 3 psi and 15 psi (scipy.constants.psi)."""
    data = relief_data_extension()
    areas = data["api526Areas"]
    assert isinstance(areas, dict)
    assert areas == pytest.approx(el.API526_AREAS, rel=1.0e-15)
    assert list(areas) == list(el.API526_AREAS)
    assert data["effectiveDischargeCoefficient"] == el.API520_EFFECTIVE_KD
    assert data["asmeOverpressureFraction"] == el.ASME_OVERPRESSURE
    assert data["asmeOverpressureFloor"] == pytest.approx(el.ASME_OVERPRESSURE_FLOOR, rel=1.0e-15)
    assert data["asmeMinimumSetPressure"] == pytest.approx(el.ASME_MINIMUM_SET, rel=1.0e-15)


def _relief_at(project: Project, rv: ReliefValve, expected: dict[str, Any]) -> dr.Ports:
    """A valve's solved ports read from a case: its flow from the pipe on its inlet port, the
    expected EGLs and the pipes' end-segment bores."""
    key_in, key_out = f"{rv.id}:inlet", f"{rv.id}:outlet"
    q = nc.port_inflow(project, key_in, expected["flows"])
    return dr.Ports(
        q,
        expected["egl"][key_in],
        expected["egl"][key_out],
        nc.port_diameter(project, key_in),
        nc.port_diameter(project, key_out),
    )


@pytest.mark.parametrize("path", RELIEF_CASES, ids=lambda p: p.stem)
def test_relief_results_follow_their_definitions(path: Path) -> None:
    """Each expected relief result from its definition at the case's own flows, EGLs and
    project (§2.2): Δp_t = ρg(h − (z_in − z_out)); the lift Q/(C√(2Δp_t/ρ)) (decision 13), 1 at
    full lift and in [0, 1); the forward law x·C·√(2Δp_t/ρ) gives Q back (closed-form cases;
    EPANET's interpolated curve to 5×10⁻⁴); setRatio, flowRatio, Δp_f and Q_f; the static drop
    is the pressures' difference and Δp_t − ρ(v_in² − v_out²)/2; the capacity's area and Kd
    (fluids' API526_A and 0.65 for a letter); the overpressure and its source; Re on the area;
    a valve without a result has no head at one side."""
    case, project = _load(path)
    expected = case["expected"]
    rho, mu, _ = nc.fluid_state(project)
    epanet = _is_epanet(case)
    for rv in _relief_valves(project):
        want = expected["reliefValves"][rv.id]
        if want is None:
            assert not all(f"{rv.id}:{p}" in expected["egl"] for p in ("inlet", "outlet"))
            continue
        at = _relief_at(project, rv, expected)
        law = el.relief_law(rv, rho)
        values = el.relief_capacity(rv.capacity, rv.set_pressure)
        h = at.egl_in - at.egl_out
        dz = nc.port_elevation(project, f"{rv.id}:inlet") - nc.port_elevation(
            project, f"{rv.id}:outlet"
        )
        dp_t = rho * dv.G * (h - dz)
        assert want["flow"] == at.q
        assert want["headLoss"] == pytest.approx(h, rel=1.0e-14, abs=1.0e-12)
        assert want["totalPressureDifference"] == pytest.approx(dp_t, rel=1.0e-12, abs=1.0e-9)
        assert want["setPressure"] == rv.set_pressure
        assert want["overpressure"] == values.overpressure
        assert want["overpressureSource"] == values.source
        assert want["setRatio"] == pytest.approx(dp_t / rv.set_pressure, rel=1.0e-12, abs=1.0e-15)
        full = rv.set_pressure * (1.0 + values.overpressure)
        q_f = values.kd * values.area * math.sqrt(2.0 * full / rho)
        assert want["fullLiftPressureDifference"] == pytest.approx(full, rel=1.0e-15)
        assert want["fullLiftFlow"] == pytest.approx(q_f, rel=1.0e-14)
        assert want["flowRatio"] == pytest.approx(at.q / q_f, rel=1.0e-14)
        if at.q == 0.0:
            assert want["state"] == "closed"
            assert want["lift"] == 0.0
            assert want["reynoldsNumber"] is None
        else:
            lift = at.q / (values.kd * values.area * math.sqrt(2.0 * dp_t / rho))
            assert want["lift"] == pytest.approx(lift, rel=1.0e-12)
            assert want["state"] == ("full_lift" if at.q >= q_f else "partial_lift")
            if want["state"] == "full_lift":
                assert lift == pytest.approx(1.0, abs=5.0e-6 if epanet else 1.0e-12)
            else:
                assert 0.0 < lift < 1.0
            forward = law.flow_at(dp_t)
            assert forward == pytest.approx(at.q, rel=5.0e-4 if epanet else 1.0e-9)
            re = rho * (at.q / values.area) * math.sqrt(4.0 * values.area / math.pi) / mu
            assert want["reynoldsNumber"] == pytest.approx(re, rel=1.0e-14)
        key_in, key_out = f"{rv.id}:inlet", f"{rv.id}:outlet"
        p_in, p_out = expected["pressures"][key_in], expected["pressures"][key_out]
        assert want["inletPressure"] == p_in
        assert want["backPressure"] == p_out
        assert want["pressureDrop"] == pytest.approx(p_in - p_out, rel=1.0e-12, abs=1.0e-9)
        v_in = nc.end_velocity(project, key_in, expected["flows"])
        v_out = nc.end_velocity(project, key_out, expected["flows"])
        identity = dp_t - rho * (v_in**2 - v_out**2) / 2.0
        assert want["pressureDrop"] == pytest.approx(identity, rel=1.0e-9, abs=1.0e-6)
        capacity = want["capacity"]
        assert capacity["kind"] == rv.capacity.kind
        assert capacity["area"] == values.area
        assert capacity["dischargeCoefficient"] == values.kd
        if rv.capacity.kind == "api526":
            assert capacity["letter"] == rv.capacity.letter
            index = fluids.safety_valve.API526_letters.index(rv.capacity.letter)
            assert values.area == pytest.approx(fluids.safety_valve.API526_A[index], rel=1.0e-15)
            assert values.kd == 0.65
        if rv.capacity.kind == "effective":
            assert capacity["coveringLetter"] == el.covering_letter(values.area)
        if rv.capacity.kind == "certified":
            assert capacity["overpressure"] == rv.capacity.overpressure


@pytest.mark.parametrize("path", RELIEF_CASES, ids=lambda p: p.stem)
def test_relief_flags_follow_their_inequalities(path: Path) -> None:
    """The relief flags of each case from its expected results (decision 15): RELIEF_VALVE_OPEN
    at full lift; CORRELATION_OUT_OF_RANGE partial_lift short of it; BELOW_VAPOR_PRESSURE on the
    valve (detail backAbsolutePressure) when it relieves with its back pressure at or below the
    vapor pressure (0 Pa absolute without one); CORRELATION_OUT_OF_RANGE viscosity when it
    relieves at μ ≥ 0.1 Pa·s; RELIEF_VALVE_CLOSED (detail side) on a valve without a result; and
    nothing else on a relief valve."""
    case, project = _load(path)
    expected = case["expected"]
    _, mu, p_vap = nc.fluid_state(project)
    p_atm = dv.standard_atmosphere_pressure(project.settings.site_elevation)
    flags = expected.get("flags", [])
    for rv in _relief_valves(project):
        own = sorted(
            (f["code"], f.get("limit") or f.get("detail") or "")
            for f in flags
            if f.get("componentId") == rv.id
            and not (f["code"] == "BELOW_VAPOR_PRESSURE" and "detail" not in f)
        )
        want = expected["reliefValves"][rv.id]
        wanted: list[tuple[str, str]] = []
        if want is None:
            wanted.append(("RELIEF_VALVE_CLOSED", "side"))
        elif want["flow"] > 0.0:
            if want["state"] == "full_lift":
                wanted.append(("RELIEF_VALVE_OPEN", ""))
            else:
                wanted.append(("CORRELATION_OUT_OF_RANGE", "partial_lift"))
            threshold = 0.0 if p_vap is None else p_vap
            if want["backPressure"] + p_atm <= threshold:
                wanted.append(("BELOW_VAPOR_PRESSURE", "backAbsolutePressure"))
            if mu >= dr.VISCOSITY_LIMIT:
                wanted.append(("CORRELATION_OUT_OF_RANGE", "viscosity"))
        assert own == sorted(wanted), (rv.id, own, wanted)


def test_relief_flag_cases_cover_every_flag() -> None:
    """Each relief flag appears in some case (decision 15)."""
    found = {
        (f["code"], f.get("limit") or f.get("detail") or "")
        for path in RELIEF_CASES
        for f in read_case(path)["expected"].get("flags", [])
        if f.get("componentId", "").startswith("RV")
    }
    assert {
        ("RELIEF_VALVE_OPEN", ""),
        ("CORRELATION_OUT_OF_RANGE", "partial_lift"),
        ("CORRELATION_OUT_OF_RANGE", "viscosity"),
        ("BELOW_VAPOR_PRESSURE", "backAbsolutePressure"),
        ("RELIEF_VALVE_CLOSED", "side"),
    } <= found


def test_relief_valve_opens_on_the_static_difference() -> None:
    """C4 (outlet port 0.5 m above the inlet port): h_set = Δp_s/(ρg) − 0.5 m, so at zero flow
    the valve opens where the static difference p_in − p_out equals Δp_s exactly (decision 5,
    §1.3 item 15), and the static and total differences differ by the velocity heads only."""
    _, project = _load(case_path("relief_port_elevations"))
    [rv] = _relief_valves(project)
    rho = nc.density(project)
    law = el.relief_law(rv, rho)
    assert law.dz == -dr.C4_OUTLET_ELEVATION
    # At zero flow both ports are at rest: EGL_in − EGL_out = h_set gives p_in − p_out = Δp_s.
    z_in, z_out = (nc.port_elevation(project, f"RV1:{p}") for p in ("inlet", "outlet"))
    h_out = 1.0
    h_in = h_out + law.h_set()
    static = dv.static_pressure(rho, h_in, z_in, 0.0) - dv.static_pressure(rho, h_out, z_out, 0.0)
    assert static == pytest.approx(rv.set_pressure, rel=1.0e-12)


def test_relief_c2_other_pressure_readings() -> None:
    """C2 at its solved pressures (proposal §1.3 item 1, S2): API 520's equation on the inlet
    stagnation and outlet static pressures (the definitions' literal reading) would pass 0.418 %
    more flow, on the static difference 1.609 % less; the total-pressure reading used lies
    between them."""
    case, project = _load(case_path("relief_partial_lift"))
    expected = case["expected"]
    [rv] = _relief_valves(project)
    rho = nc.density(project)
    law = el.relief_law(rv, rho)
    at = _relief_at(project, rv, expected)
    p_in, p_out = expected["pressures"]["RV1:inlet"], expected["pressures"]["RV1:outlet"]
    literal = law.flow_at(p_in + rho * at.v_in**2 / 2.0 - p_out)
    static = law.flow_at(p_in - p_out)
    assert literal / at.q - 1.0 == pytest.approx(0.00418, abs=5.0e-6)
    assert static / at.q - 1.0 == pytest.approx(-0.01609, abs=5.0e-6)


def test_relief_c3_is_api520_at_the_solved_state() -> None:
    """C3 beyond full lift: fluids' API520_A_l at the solved flow with P1 − P2 = Δp_t (= ρgh,
    the ports level) gives API 526 F's area times 1 + 6.0921×10⁻⁵ (proposal §7.1)."""
    case, project = _load(case_path("relief_full_lift"))
    want = case["expected"]["reliefValves"]["RV1"]
    rho = nc.density(project)
    required = fluids.safety_valve.API520_A_l(
        m=rho * want["flow"],
        rho=rho,
        P1=want["totalPressureDifference"] + 101325.0,
        P2=101325.0,
        overpressure=0.1,
        Kd=0.65,
        Kc=1.0,
        Kw=1.0,
        Kv=1.0,
    )
    assert required / el.API526_AREAS["F"] - 1.0 == pytest.approx(API520_ROUNDING, rel=1.0e-7)


def test_epanet_relief_cases_agree_with_the_closed_form() -> None:
    """EPANET's GPV runs (proposal §7.2) against the closed form of network M in EPANET water
    with the suite's Swamee–Jain: within 2×10⁻⁴ in the relief flow (EPANET's g in the pipes, the
    interpolated curve). The proposal's measured EPANET flows, its reference flows times 1 + ΔQ
    (E1 0.0022186660463 × (1 + 1.702×10⁻⁴), E2 0.0047276688973 × (1 + 1.038×10⁻⁵), E3
    0.0010820268256 × (1 + 1.629×10⁻⁴)), are EPANET's here to their four printed digits of ΔQ
    (half a unit of the fourth digit is 5×10⁻⁸ of the flow at most)."""
    rho, mu, _ = dv.fluid_state(do.epanet_water())
    printed = {
        "epanet_relief_partial": (1.05e6, 0.0022186660463, 1.702e-4),
        "epanet_relief_full": (1.4e6, 0.0047276688973, 1.038e-5),
        "epanet_relief_near_set": (1.004e6, 0.0010820268256, 1.629e-4),
    }
    for name, (p_r, reference, delta) in printed.items():
        q = read_case(case_path(name))["expected"]["flows"]["LB1"]
        closed = dr.network_m(p_r).solve(rho, mu, "swamee_jain").q_relief
        assert abs(q / closed - 1.0) < 2.0e-4, name
        assert q == pytest.approx(reference * (1.0 + delta), rel=6.0e-8), name


RELIEF_PROPOSAL_VALUES: dict[str, list[tuple[str, str, float]]] = {
    "relief_closed": [("pressures", "RV1:inlet", 319_574.0734)],
    "relief_partial_lift": [
        ("flows", "LB1", 0.002221210802348),
        ("reliefValves.RV1", "lift", 0.5311270926),
        ("reliefValves.RV1", "flowRatio", 0.5196842317),
        ("egl", "RV1:inlet", 53.81168955),
        ("egl", "RV1:outlet", 0.01028154777),
        ("pressures", "RV1:inlet", 526_131.6131),
        ("pressures", "RV1:outlet", -7.754453834),
        ("reliefValves.RV1", "totalPressureDifference", 526_556.3546),
        ("reliefValves.RV1", "pressureDrop", 526_139.3676),
    ],
    "relief_full_lift": [
        ("flows", "LB1", 0.004732647684257),
        ("reliefValves.RV1", "flowRatio", 1.107271031),
        ("pressures", "RV1:inlet", 672_346.5806),
        ("reliefValves.RV1", "headLoss", 68.90002007),
        ("reliefValves.RV1", "fullLiftFlow", 0.004274154702),
    ],
    "relief_port_elevations": [
        ("flows", "LB1", 0.002466109033239),
        ("reliefValves.RV1", "lift", 0.5880976056),
        ("pressures", "RV1:inlet", 523_985.4996),
        ("pressures", "RV1:outlet", -4_905.375361),
        ("reliefValves.RV1", "pressureDrop", 528_890.875),
    ],
    "relief_asme_3psi": [
        ("reliefValves.RV1", "overpressure", 0.1378951459),
        ("flows", "LB1", 0.001473859256618),
        ("reliefValves.RV1", "lift", 0.6332320359),
        ("reliefValves.RV1", "flowRatio", 0.6189996008),
        ("pressures", "RV1:inlet", 162_914.5764),
    ],
    "relief_pump_bypass": [
        ("flows", "LB1", 0.02530885872613),
        ("reliefValves.RV1", "lift", 0.7913442325),
        ("reliefValves.RV1", "flowRatio", 0.7838029109),
        ("pressures", "RV1:inlet", 367_016.2267),
        ("reliefValves.RV1", "setRatio", 1.07913442325),
        ("reliefValves.RV1", "setPressure", 330_425.9266),
    ],
    "relief_set_above_shutoff": [("pressures", "RV1:inlet", 459_990.7249)],
    "relief_parallel_staggered": [
        ("flows", "LA1", 0.01460771747274),
        ("flows", "LB1", 0.00964240706616),
        ("reliefValves.RVb", "lift", 0.658683),
        ("egl", "T2:run_inlet", 39.6433689),
    ],
    "relief_assigned_demand": [
        ("reliefValves.RV1", "headLoss", 54.72182215),
        ("reliefValves.RV1", "lift", 0.71128963),
        ("egl", "RV1:outlet", 8.4999204),
        ("pressures", "AF1:port_1", 82_817.09534),
    ],
    "relief_assigned_demand_low_supply": [
        ("egl", "RV1:outlet", -6.826475587),
        ("pressures", "AF1:port_1", -67_182.90466),
    ],
    "relief_locked_closed": [("pressures", "RV1:inlet", 459_990.7249)],
    "relief_certified": [
        ("reliefValves.RV1", "fullLiftFlow", 0.005756846582),
        ("flows", "LB1", 0.002921930523253),
        ("reliefValves.RV1", "lift", 0.5168904272),
        ("reliefValves.RV1", "flowRatio", 0.5075574764),
        ("pressures", "RV1:inlet", 519_932.5011),
    ],
}
"""Values of each case as the proposal's §7.1 table prints them (10-13 significant digits, the
C8 lift six), measured by its designers with the law placed in a check valve's link of the real
solver, and independently by its first reviewer: a second route to each derivation. C8's RVa set
differs from the proposal's (module docstring of derivations_relief); beyond full lift its flow
does not depend on the set, so the printed flows and head hold."""


@pytest.mark.parametrize("name", sorted(RELIEF_PROPOSAL_VALUES))
def test_relief_derivations_reproduce_the_proposal(name: str) -> None:
    expected = read_case(case_path(name))["expected"]
    for group, key, value in RELIEF_PROPOSAL_VALUES[name]:
        where: Any = expected
        for part in group.split("."):
            where = where[part]
        digits = len(f"{abs(value):.15g}".replace(".", "").lstrip("0").rstrip("0"))
        assert where[key] == pytest.approx(value, rel=max(1.0e-12, 0.6 * 10.0 ** (1 - digits))), (
            name,
            group,
            key,
            where[key],
        )
