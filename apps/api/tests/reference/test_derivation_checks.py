"""Self-checks of the reference cases themselves, independent of the solver.

- Friction-factor paths: Colebrook (Lambert W) against Clamond; the constants and slopes used in
  the transition interpolation; the Hermite transition against EPANET 2.2's own Dunlop
  polynomial when fed EPANET's Swamee–Jain.
- Every case file: a valid Project; energy equations re-evaluated from the *project JSON* close
  with the expected values; continuity holds; ideal-tee ports share one EGL; expected pressures
  follow p = ρ g (H − z − v²/2g).
- Second routes to the answers: the parallel split by nested brentq (the case uses fsolve), and a
  whole-network fsolve of every case from a perturbed start.
- EPANET cases: residuals vanish under EPANET's constants (g = 32.2 ft/s², minor-loss constant
  0.02517, its friction code) to float32 precision, and our model's answer stays well inside the
  0.5 % criterion of EPANET's.
"""

import math
from pathlib import Path
from typing import Any

import fluids.friction
import numpy as np
import pytest
from scipy.optimize import brentq

from opensolve_pipe.models.components import TeeBranch
from opensolve_pipe.models.project import Project
from tests.reference import derivations as dv
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
    if _is_epanet(case):
        model = nc.EPANET_MODEL
        nu = nc.kinematic_viscosity(project)
        losses = [
            abs(nc.connection_head_loss(c, expected["flows"][c.id], nu, model))
            for c in project.connections
        ]
        # float32 rounding of the heads and flows EPANET reports, with a few ulps of margin.
        heads = max(abs(h) for h in expected["egl"].values())
        tolerance = 8 * FLOAT32_REL * (heads + max(losses))
    else:
        model = nc.our_model(project)
        tolerance = 1.0e-11
    residuals = nc.energy_residuals(project, expected["flows"], expected["egl"], model)
    assert max(abs(r) for r in residuals.values()) <= tolerance, residuals


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
        if isinstance(component, TeeBranch):
            values = {egl[f"{component.id}:{p.id}"] for p in component.ports}
            assert len(values) == 1, component.id
    # Every port of the project has an expected EGL.
    assert set(egl) == {f"{c.id}:{p.id}" for c in project.components for p in c.ports}


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
    flows, egl = nc.solve_network(project, nc.our_model(project), guess_q, guess_h)
    for key, q in expected["flows"].items():
        assert flows[key] == pytest.approx(q, rel=1.0e-9, abs=1.0e-15), key
    for key, h in expected["egl"].items():
        assert egl[key] == pytest.approx(h, abs=1.0e-9), key


@pytest.mark.parametrize(
    "path", [p for p in CASES if p.stem.startswith("epanet")], ids=lambda p: p.stem
)
def test_epanet_case_agrees_with_our_model_inside_the_criterion(path: Path) -> None:
    """Our model (g = 9.80665, exact minor-loss constant, fluids' Swamee–Jain) solved as a
    network lands within 0.2 % of EPANET in every flow and 1 mm in every head, so EPANET's
    built-in constants use well under half of the 0.5 % criterion."""
    case, project = _load(path)
    expected = case["expected"]
    flows, egl = nc.solve_network(
        project, nc.our_model(project), expected["flows"], expected["egl"]
    )
    for key, q in expected["flows"].items():
        assert flows[key] == pytest.approx(q, rel=2.0e-3), key
    for key, h in expected["egl"].items():
        assert egl[key] == pytest.approx(h, abs=1.0e-3), key


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
    assert regimes("transitional_flow_colebrook") == {"transitional"}
    assert regimes("single_pipe_turbulent") == {"turbulent"}
    assert regimes("epanet_looped_network_b") == {"laminar", "transitional", "turbulent"}
