"""Flow-controlled pump scenarios that are not case files (CLAUDE.md D11; proposal
docs/proposals/vfd-pump-modes.md §4.3, §4.6, §5, §7.1 CF10, CF16, CF18).

A case file needs a converged solve with an EGL at every port outside an isolated section and
a result for every pump; these scenarios have none of that by design:

- over-control (§4.6, §5): two flow-controlled pumps in series with equal setpoints, or a
  flow-controlled pump and an FCV with equal setpoints, both able to hold the common flow. One
  flow passes both, so with both active any split of the system head between them (inside
  their ranges) satisfies every equation and rule: the speeds and the pressure between them
  are not determined by the inputs. The solve must end not converged and name both (AFT
  "no solution", PIPE-FLO "Over Controlled", as the proposal cites);
- isolated (§5, CF16): a flow-controlled pump between two closed isolation valves sees no flow
  path, so its controller runs to maximum speed (rule A0): it is the fixed-speed pump at s_max
  inside a closed-off section, which has no pump result and raises no pump flag, exactly like
  the fixed-speed pump;
- a curve whose speed is not unique (§4.3, CF18): ψ(x) = 2H₀(x) − x H₀'(x) ≤ 0 inside the
  curve's points means F(s, Q) = s² H₀(Q/s) falls with s somewhere (d/ds F = s ψ(Q/s)), so a
  flow there can be held at two speeds: a controlled pump on such a curve is the 422 topology
  issue CONTROLLED_PUMP_CURVE (SDD §5.1.2 error envelope), while a fixed-speed pump on the same
  curve is not (the rule is about the speed's uniqueness only);
- a setpoint beyond the curve even at maximum speed (owner's decision 2026-10-23, TSD §12
  decided item 7, was open item 5): Q_set ≥ s_max · x_mono means F(·, Q_set) falls at every
  speed of the drive, so no speed controls it and two limit states both satisfy the rules: the
  422 topology issue CONTROLLED_PUMP_SETPOINT, in the owner's exact words, for a curve that
  passes the ψ test; just below the bound the setpoint is solved, and a curve whose end tangent
  does not fall never triggers it.

Expected values are derived here or in ``derivations_pump_control`` from closed forms, never
from the solver.
"""

import math
import re
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from scipy.interpolate import PchipInterpolator

from opensolve_pipe.models.api import SolveResponse
from opensolve_pipe.models.components import Pump, PumpControl
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.pumps import PumpCurve
from opensolve_pipe.services.solver import solve_project
from tests.reference import derivations as dv
from tests.reference import derivations_pump_control as dpc
from tests.reference import element_laws as el
from tests.reference.case_format import (
    control_valve,
    custom_fluid,
    flow_control,
    ideal_tee,
    isolation_valve,
    make_project,
    pump,
    pump_curve,
    reservoir,
)
from tests.reference.derivations_pumps import DISCHARGE_A, SUCTION_A, curve_a, curve_b
from tests.reference.line import Line

NU = dv.FLUID_A[2] / dv.FLUID_A[1]
RELATIVE = 0.005
FLOW_FLOOR = 1.0e-9
HEAD_FLOOR = 0.01  # m


# --- Over-control ---------------------------------------------------------------------------------


def test_series_flow_pumps_with_equal_setpoints_are_not_converged() -> None:
    """CF10, equal setpoints: P1 (curve_b, s ∈ [0.6, 1]) and P2 (curve_a, s ∈ [0.5, 1]) in
    series, both set to 0.02 m³/s, lifting to R2 at 40 m. Both active needs H₁ + H₂ = Sys(Q_set)
    with F_i(s_min, Q_set) ≤ H_i ≤ F_i(s_max, Q_set): Sys(Q_set) lies clearly inside
    (ΣF_i(s_min), ΣF_i(s_max)), so a continuum of splits holds."""
    q = 0.02
    chain = dpc.series_pumps(40.0, q, q)
    p1, p2 = chain.elements
    assert isinstance(p1, Pump)
    assert isinstance(p2, Pump)
    assert p1.control is not None
    assert p2.control is not None
    ca, cb = curve_a(), curve_b()
    sys_q = chain.system_head(q, NU)
    low = el.pump_head(cb, p1.control.min_speed, q) + el.pump_head(ca, p2.control.min_speed, q)
    high = el.pump_head(cb, p1.speed, q) + el.pump_head(ca, p2.speed, q)
    assert low + el.STATE_MARGIN < sys_q < high - el.STATE_MARGIN
    project = chain.project(
        "pump_flow_control_series_equal",
        "Flow-controlled pumps in series, equal setpoints",
        [cb, ca],
    )

    result = solve_project(project)

    assert not result.converged
    assert "P1" in result.convergence.message
    assert "P2" in result.convergence.message


def test_flow_pump_and_fcv_with_equal_setpoints_are_not_converged() -> None:
    """A flow-controlled pump (curve_a, Q_set 0.02 m³/s, s ∈ [0.5, 1]) in series with an FCV
    set to the same flow, on a line whose system head at that flow is clearly below F(s_max,
    Q_set): any pump head in [max(F(s_min, Q_set), Sys), F(s_max, Q_set)] with the FCV dropping
    the excess holds both, so the split is undetermined."""
    q = 0.02
    curve = curve_a()
    pu1 = pump("PU1", 0.5, curve.id, control=flow_control(q, 0.5))
    fcv1 = control_valve("FCV1", 0.5, "fcv", q)
    chain = dpc.Series(
        0.0,
        3.0,
        18.0,
        2.0,
        [SUCTION_A, dpc.SERIES_BETWEEN, DISCHARGE_A],
        [pu1, fcv1],
    )
    assert el.pump_head(curve, pu1.speed, q) - chain.system_head(q, NU) > el.STATE_MARGIN
    project = chain.project(
        "pump_flow_control_fcv_equal",
        "Flow-controlled pump and FCV in series, equal setpoints",
        [curve],
    )

    result = solve_project(project)

    assert not result.converged
    assert "PU1" in result.convergence.message
    assert "FCV1" in result.convergence.message


# --- Isolated -------------------------------------------------------------------------------------


def isolated_pump_project(controlled: bool) -> Project:
    """R1 (H 10 m) → L1 → T1 → LA → T2 → L4 → R2 (H 1 m), with a bypass T1:branch → LB1 → IV1
    (isolated) → LB2 → PU1 → LB3 → IV2 (isolated) → LB4 → T2:branch; PU1 flow-controlled
    (curve_a, Q_set 0.01 m³/s, s ∈ [0.5, 0.9]) or the fixed-speed pump at its maximum 0.9."""
    control = flow_control(0.01, 0.5) if controlled else None
    curve = curve_a()
    l1 = Line(0.1023, 50.0, (("entrance_sharp", 1),))
    la = Line(0.0779, 80.0)
    l4 = Line(0.1023, 60.0, (("exit", 1),))
    lb = Line(0.0525, 10.0)
    return make_project(
        f"ref-pump-flow-control-isolated-{'controlled' if controlled else 'fixed'}",
        "Pump between two closed valves",
        custom_fluid(*dv.FLUID_A),
        [
            reservoir("R1", 8.0, 2.0),
            ideal_tee("T1", 2.0),
            isolation_valve("IV1", 1.8, "gate", status="isolated"),
            pump("PU1", 1.8, curve.id, speed=0.9, control=control),
            isolation_valve("IV2", 1.8, "gate", status="isolated"),
            ideal_tee("T2", 1.5),
            reservoir("R2", 0.0, 1.0),
        ],
        [
            l1.connect("L1", "R1:port_1", "T1:run_inlet"),
            la.connect("LA", "T1:run_outlet", "T2:run_inlet"),
            l4.connect("L4", "T2:run_outlet", "R2:port_1"),
            lb.connect("LB1", "T1:branch", "IV1:inlet"),
            lb.connect("LB2", "IV1:outlet", "PU1:suction"),
            lb.connect("LB3", "PU1:discharge", "IV2:inlet"),
            lb.connect("LB4", "IV2:outlet", "T2:branch"),
        ],
        pump_library=[curve],
    )


def _flag_keys(flags: Any) -> set[tuple[str, str | None, str | None]]:
    return {(f.code, f.component_id, f.connection_id) for f in flags}


def test_flow_controlled_pump_between_closed_valves_is_the_fixed_pump() -> None:
    """CF16: no pump result and no pump flag, as the fixed-speed pump at s_max; the main line
    carries H_R1 − H_R2 = h_L1(Q) + h_LA(Q) + h_L4(Q) (brentq) and the bypass nothing."""
    project = isolated_pump_project(controlled=True)
    lines = {c.id: c for c in project.connections}
    l1 = Line(0.1023, 50.0, (("entrance_sharp", 1),))
    la = Line(0.0779, 80.0)
    l4 = Line(0.1023, 60.0, (("exit", 1),))
    assert set(lines) == {"L1", "LA", "L4", "LB1", "LB2", "LB3", "LB4"}
    q = dv.solve_flow(
        lambda x: l1.head_loss(x, NU) + la.head_loss(x, NU) + l4.head_loss(x, NU), 10.0 - 1.0
    )

    result = solve_project(project)
    fixed = solve_project(isolated_pump_project(controlled=False))

    assert result.converged, result.convergence.message
    assert fixed.converged, fixed.convergence.message
    for cid in ("L1", "LA", "L4"):
        got = result.link_results[cid].flow
        assert abs(got - q) <= max(RELATIVE * q, FLOW_FLOOR), cid
    for cid in ("LB1", "LB2", "LB3", "LB4"):
        assert result.link_results[cid].flow == 0.0, cid
    assert "PU1" not in result.pump_results
    assert "PU1" not in fixed.pump_results
    assert not [f for f in result.flags if f.component_id == "PU1"]
    isolated = [f for f in result.flags if f.code == "ISOLATED_SECTION"]
    assert any("PU1" in str(f.details.get("componentIds", "")).split(", ") for f in isolated)
    # Equal to the fixed-speed pump at its maximum speed: flows, heads and flags.
    assert _flag_keys(result.flags) == _flag_keys(fixed.flags)
    assert set(result.node_results) == set(fixed.node_results)
    for cid, link in result.link_results.items():
        assert link.flow == pytest.approx(fixed.link_results[cid].flow, rel=1.0e-12, abs=0.0)
    for key, node in result.node_results.items():
        assert node.egl == pytest.approx(fixed.node_results[key].egl, rel=1.0e-12)


# --- Curve uniqueness (CONTROLLED_PUMP_CURVE) ---------------------------------------------------


def _steep_curve_project(controlled: bool) -> Project:
    """R1 (H 3 m) → suction → PU1 on ``curve_steep_rise`` → discharge → R2 (H 8 m); PU1
    flow-controlled (Q_set 0.015 m³/s, s ∈ [0.5, 1]) or fixed at rated speed."""
    curve = dpc.curve_steep_rise()
    control = flow_control(0.015, 0.5) if controlled else None
    return make_project(
        f"ref-pump-flow-control-steep-{'controlled' if controlled else 'fixed'}",
        "Pump on a curve with a steep rise",
        custom_fluid(*dv.FLUID_A),
        [
            reservoir("R1", 0.0, 3.0),
            pump("PU1", 0.5, curve.id, control=control),
            reservoir("R2", 6.0, 2.0),
        ],
        [
            SUCTION_A.connect("L1", "R1:port_1", "PU1:suction"),
            DISCHARGE_A.connect("L2", "PU1:discharge", "R2:port_1"),
        ],
        pump_library=[curve],
    )


def _post_solve(project: Project) -> Any:
    from opensolve_pipe.main import app

    body = {"project": project.model_dump(mode="json", exclude_none=True)}
    with TestClient(app) as client:
        return client.post("/api/v1/solve", json=body)


def test_controlled_pump_on_a_curve_with_psi_below_zero_is_a_topology_issue() -> None:
    """CF18 (rejected half): ψ ≤ 0 inside the curve's points (checked exactly by
    ``psi_minimum``) gives HTTP 422 TOPOLOGY_ERROR with a CONTROLLED_PUMP_CURVE issue naming
    the pump; the same curve on a fixed-speed pump is no topology issue."""
    curve = dpc.curve_steep_rise()
    assert dpc.psi_minimum(curve, 0.0, curve.points[-1].flow) <= 0.0

    response = _post_solve(_steep_curve_project(controlled=True))

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["success"] is False
    assert body["error"] == "TOPOLOGY_ERROR"
    issues = [i for i in body["issues"] if i["code"] == "CONTROLLED_PUMP_CURVE"]
    assert issues, body
    assert any("PU1" in i["componentIds"] for i in issues)
    assert _post_solve(_steep_curve_project(controlled=False)).status_code == 200


# --- Setpoint beyond the curve at maximum speed (CONTROLLED_PUMP_SETPOINT) ----------------------
#
# Owner's decision (2026-10-23), from proposal vfd-pump-modes.md §4.3: d/ds F(s, Q) = s ψ(Q/s),
# ψ(x) = 2H₀(x) − x H₀'(x). Beyond the last point (x_e, h_e) H₀ is the end tangent
# h_e + m (x − x_e), m the PCHIP's slope at x_e, so ψ(x) = 2h_e + m (x − 2x_e): for m < 0 it is
# zero at x_mono = 2x_e − 2h_e/m = 2(x_e + h_e/|m|), twice the tangent's zero-head flow, and
# negative beyond; for m ≥ 0 it only grows (x_mono = ∞). With Q_set ≥ s_max · x_mono, every speed
# s ≤ s_max has Q_set/s ≥ x_mono, so F(·, Q_set) falls on the whole speed range: no speed
# controls the flow, and the input is rejected (422 TOPOLOGY_ERROR, CONTROLLED_PUMP_SETPOINT).
# Just below, Q_set/s_max < x_mono and F(·, Q_set) still rises near s_max: a valid setpoint.
#
# The line (test inputs): R1 (H 3 m) → SUCTION_A → PU1 (s ∈ [0.5, s_max]) → DISCHARGE_A → R2
# (H 20 m), the pump_single_pipe line. Its static lift, 17 m, is above the shutoff head at
# s_min, 0.25 · H₀(0) (10 m for curve_straight, 11.25 m for curve_a), so the pump at s_min
# passes nothing; it is below the shutoff head at s_max (25.6 m, 36.45 m).

SETPOINT_RULE_MIN_SPEED = 0.5
SETPOINT_RULE_STEP = 1.0e-6
"""Relative distance of the setpoints tested either side of the bound s_max · x_mono."""
SETPOINT_BOUND = re.compile(r"setpoints must be below (\S+) m³/s")


def end_slope(curve: PumpCurve) -> float:
    """m = H₀'(x_e): the slope of scipy's PchipInterpolator through the rated points at the
    last point, the slope of the straight extension beyond it (design §2.2)."""
    xs = [p.flow for p in curve.points]
    pchip = PchipInterpolator(xs, [p.head for p in curve.points])
    return float(pchip.derivative()(xs[-1]))


def x_mono_of(curve: PumpCurve) -> float:
    """x_mono = 2x_e − 2h_e/m on a falling end tangent (m < 0), else ∞ (section comment)."""
    last = curve.points[-1]
    m = end_slope(curve)
    return 2.0 * last.flow - 2.0 * last.head / m if m < 0.0 else math.inf


def setpoint_issue_message(
    pump_id: str, q_set: float, speed: float, curve: PumpCurve, x_mono: float
) -> str:
    """The CONTROLLED_PUMP_SETPOINT message, in the format the owner fixed (2026-10-23)."""
    return (
        f"pump '{pump_id}' is speed-controlled to hold {q_set:.6g} m³/s, but no speed up to "
        f"its maximum speed {speed:.6g} can hold it on its curve '{curve.id}' ({curve.name}): "
        "at that flow the head s² H₀(Q/s) falls as the speed s rises, at every speed, because "
        f"Q/s lies beyond x_mono = {x_mono:.6g} m³/s, twice the flow at which the curve's end "
        f"tangent reaches zero head; setpoints must be below {speed * x_mono:.6g} m³/s (the "
        "maximum speed × x_mono), so use a smaller setpoint or a curve that extends to higher "
        "flows"
    )


def _setpoint_project(curve: PumpCurve, speed: float, setpoint: float) -> Project:
    """The section's line with PU1 flow-controlled to ``setpoint`` on ``curve``, s ∈ [0.5,
    speed]."""
    control = flow_control(setpoint, SETPOINT_RULE_MIN_SPEED)
    return make_project(
        f"ref-pump-flow-control-setpoint-{curve.id.lower()}",
        "Flow-controlled pump near its setpoint bound",
        custom_fluid(*dv.FLUID_A),
        [
            reservoir("R1", 0.0, 3.0),
            pump("PU1", 0.5, curve.id, speed=speed, control=control),
            reservoir("R2", 18.0, 2.0),
        ],
        [
            SUCTION_A.connect("L1", "R1:port_1", "PU1:suction"),
            DISCHARGE_A.connect("L2", "PU1:discharge", "R2:port_1"),
        ],
        pump_library=[curve],
    )


def curve_rising_end() -> PumpCurve:
    """A curve that dips and rises at its last point (test input). scipy's PCHIP slope is 0 at
    the dip (0.02 m³/s: the secants −400 and +50 m/(m³/s) on either side change sign) and its
    one-sided end slope (3 · 50 − (−400))/2 = 275 is clipped to 3 · 50 = 150 (the secants
    change sign and |275| > 3 · 50): the end tangent rises, x_mono = ∞. ψ > 0 on the points."""
    return pump_curve("PC-UP", [(0.0, 40.0), (0.01, 38.0), (0.02, 34.0), (0.03, 34.5)])


def curve_flat_end() -> PumpCurve:
    """A curve whose last two points have one head (test input): the last secant is 0, so
    scipy's PCHIP end slope is 0 (its sign differs from the secant's): a flat end tangent,
    x_mono = ∞. ψ > 0 on the points."""
    return pump_curve("PC-FLAT", [(0.0, 40.0), (0.01, 38.0), (0.02, 34.0), (0.03, 34.0)])


FALLING_END_CURVES: list[tuple[Callable[[], PumpCurve], float, float]] = [
    # curve_straight, H₀ = 40 − 400 x: PCHIP reproduces collinear points, so m = −400 and
    # x_mono = 2(0.04 + 24/400) = 0.2 m³/s = 2a/b; s_max = 0.8 (test input), bound 0.16 m³/s.
    (dpc.curve_straight, 0.8, 0.2),
    # curve_a (equal spacing h = 0.01): scipy's one-sided end slope ((2h + h) δ₄ − h δ₃)/(2h)
    # = (3 δ₄ − δ₃)/2 with δ₄ = (27 − 35.5)/0.01 = −850 and δ₃ = (35.5 − 41)/0.01 = −550 gives
    # m = −1000 (δ₄'s sign, |m| ≤ 3|δ₄|: not clipped), x_mono = 2(0.04 + 27/1000) = 0.134 m³/s
    # (proposal §4.3's check); s_max = 0.9 (test input), bound 0.1206 m³/s.
    (curve_a, 0.9, 0.134),
]


@pytest.mark.parametrize(
    ("make_curve", "speed", "x_mono_closed_form"),
    FALLING_END_CURVES,
    ids=lambda v: v.__name__ if callable(v) else str(v),
)
def test_flow_setpoint_beyond_the_curve_at_maximum_speed_is_a_topology_issue(
    make_curve: Callable[[], PumpCurve], speed: float, x_mono_closed_form: float
) -> None:
    """Q_set = s_max · x_mono · (1 + 1e-6): HTTP 422 TOPOLOGY_ERROR whose only issue is
    CONTROLLED_PUMP_SETPOINT naming the pump, the bound in its message s_max · x_mono to six
    significant digits, the message the owner's format with the values derived here."""
    curve = make_curve()
    x_mono = x_mono_of(curve)
    assert x_mono == pytest.approx(x_mono_closed_form, rel=1.0e-12)
    assert x_mono == pytest.approx(el.x_mono(curve), rel=1.0e-12)
    # The curve passes the ψ test, so the setpoint check runs (owner: after it).
    assert dpc.psi_minimum(curve, 0.0, curve.points[-1].flow) > 0.0
    bound = speed * x_mono
    q_set = bound * (1.0 + SETPOINT_RULE_STEP)
    # Q_set/s_max lies on the end tangent beyond x_mono: ψ < 0 there, and at every lower speed.
    assert q_set / speed > x_mono > curve.points[-1].flow
    assert dpc.psi(curve, q_set / speed) < 0.0

    response = _post_solve(_setpoint_project(curve, speed, q_set))

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["success"] is False
    assert body["error"] == "TOPOLOGY_ERROR"
    assert [i["code"] for i in body["issues"]] == ["CONTROLLED_PUMP_SETPOINT"], body
    [issue] = body["issues"]
    assert issue["componentIds"] == ["PU1"]
    found = SETPOINT_BOUND.search(issue["message"])
    assert found is not None, issue["message"]
    assert found.group(1) == f"{bound:.6g}"
    assert issue["message"] == setpoint_issue_message("PU1", q_set, speed, curve, x_mono)


@pytest.mark.parametrize(
    ("make_curve", "speed", "x_mono_closed_form"),
    FALLING_END_CURVES,
    ids=lambda v: v.__name__ if callable(v) else str(v),
)
def test_flow_setpoint_just_below_the_bound_is_solved(
    make_curve: Callable[[], PumpCurve], speed: float, x_mono_closed_form: float
) -> None:
    """Q_set = s_max · x_mono · (1 − 1e-6): not rejected. The state is not asserted (near the
    bound the drive's band [F(s_lo, Q_set), F(s_max, Q_set)] is a few 1e-11 m wide); the
    result must satisfy the rules of proposal §4.5 exactly (``controlled_pump_state_problem``
    with margin −Htol) at its reported flow and EGL rise, run at the speed its state gives, and
    lie on the pump's law and on the line's system head, H = H_R2 − H_R1 + h_L1(Q) + h_L2(Q)
    (D6: 0.5 % or 0.01 m)."""
    curve = make_curve()
    assert x_mono_of(curve) == pytest.approx(x_mono_closed_form, rel=1.0e-12)
    q_set = speed * x_mono_of(curve) * (1.0 - SETPOINT_RULE_STEP)
    assert dpc.psi(curve, q_set / speed) > 0.0  # F(·, Q_set) still rises at s_max
    control = flow_control(q_set, SETPOINT_RULE_MIN_SPEED)

    response = _post_solve(_setpoint_project(curve, speed, q_set))

    assert response.status_code == 200, response.text
    state = SolveResponse.model_validate(response.json()).solved_state
    assert state.converged, state.convergence.message
    got = state.pump_results["PU1"]
    assert got.control is not None
    q = got.operating_flow
    lift = state.node_results["PU1:discharge"].egl - state.node_results["PU1:suction"].egl
    problem = el.controlled_pump_state_problem(
        "on", curve, control, speed, got.control.state, q, lift, -el.HTOL, q_abs_tol=el.QTOL
    )
    assert problem is None, f"PU1 {problem}: Q = {q!r}, H = {lift!r}"
    limit_speed = el.control_state_speed(control, speed, got.control.state)
    if limit_speed is not None:
        assert got.speed == pytest.approx(limit_speed, rel=1.0e-12)
    if got.status == "running":
        want = el.pump_head(curve, got.speed, q)
        assert abs(lift - want) <= max(RELATIVE * abs(want), HEAD_FLOOR), (lift, want)
    system = 20.0 - 3.0 + SUCTION_A.head_loss(q, NU) + DISCHARGE_A.head_loss(q, NU)
    assert abs(lift - system) <= max(RELATIVE * abs(system), HEAD_FLOOR), (lift, system)


def test_flow_setpoint_check_runs_only_on_curves_that_pass_the_psi_test() -> None:
    """``curve_steep_rise`` fails the ψ test and has a falling end tangent (x_mono finite): a
    setpoint 1.5 × s_max · x_mono gives CONTROLLED_PUMP_CURVE and no CONTROLLED_PUMP_SETPOINT
    (owner: the setpoint check runs after the ψ test, for a curve that passes it)."""
    curve = dpc.curve_steep_rise()
    assert dpc.psi_minimum(curve, 0.0, curve.points[-1].flow) <= 0.0
    x_mono = x_mono_of(curve)
    assert math.isfinite(x_mono)
    assert x_mono == pytest.approx(el.x_mono(curve), rel=1.0e-12)

    response = _post_solve(_setpoint_project(curve, 1.0, 1.5 * x_mono))

    assert response.status_code == 422, response.text
    codes = [i["code"] for i in response.json()["issues"]]
    assert "CONTROLLED_PUMP_CURVE" in codes
    assert "CONTROLLED_PUMP_SETPOINT" not in codes


SETPOINT_MAXIMUM = float(PumpControl.model_json_schema()["properties"]["setpoint"]["maximum"])
"""The largest setpoint the model accepts, m³/s (its published schema bound)."""


@pytest.mark.parametrize("make_curve", [curve_rising_end, curve_flat_end], ids=lambda f: f.__name__)
@pytest.mark.parametrize("setpoint", [0.05, 1.0, SETPOINT_MAXIMUM])
def test_flow_setpoint_on_a_curve_whose_end_tangent_does_not_fall_is_never_rejected(
    make_curve: Callable[[], PumpCurve], setpoint: float
) -> None:
    """An end tangent with m ≥ 0 keeps ψ(x) = 2h_e + m (x − 2x_e) ≥ ψ(x_e) > 0 at every flow
    beyond the points, so F(·, Q) rises with the speed at every setpoint: no setpoint up to the
    model's maximum is rejected (owner: x_mono infinite never triggers the check). s_max = 0.9;
    0.05 m³/s already puts Q_set/s_max beyond the last point. Only the absence of a topology
    issue is asserted: on a curve that rises again the operating state is not the subject."""
    curve = make_curve()
    assert end_slope(curve) >= 0.0
    assert x_mono_of(curve) == math.inf
    assert el.x_mono(curve) == math.inf
    assert dpc.psi_minimum(curve, 0.0, curve.points[-1].flow) > 0.0
    assert setpoint / 0.9 > curve.points[-1].flow

    response = _post_solve(_setpoint_project(curve, 0.9, setpoint))

    assert response.status_code == 200, response.text


# --- Zero-flow re-test path ---------------------------------------------------------------------


def test_zero_flow_reopen_case_reopens_the_pump_with_its_check_valve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``pump_flow_control_zero_flow_reopen`` keeps exercising the path it is named for: the
    flow-controlled pump and its check valve close together, and the outer loop's zero-flow
    re-test of closed elements around a closed-off section (CLAUDE.md D9, proposal §5)
    re-opens both. Its values are checked against the case file (closed form) by
    ``test_reference_cases``; this test only records what the re-test returns, so that the
    case cannot stop reaching it unnoticed (``pump_flow_control_check_valve_reopen`` never
    does: its pump starts as a fixed flow and its check valve stays open)."""
    from opensolve_pipe.services.solver import status

    reopened: list[set[str]] = []
    retest = status.zero_flow_openings

    def recording_retest(*args: Any, **kwargs: Any) -> Any:
        out = retest(*args, **kwargs)
        reopened.append(set(out))
        return out

    monkeypatch.setattr(status, "zero_flow_openings", recording_retest)

    result = solve_project(dpc.pump_flow_control_zero_flow_reopen().project)

    assert result.converged, result.convergence.message
    assert any({"PU1", "CV1"} <= ids for ids in reopened), reopened
