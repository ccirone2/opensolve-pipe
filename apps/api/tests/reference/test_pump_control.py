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
  curve is not (the rule is about the speed's uniqueness only).

Expected values are derived here or in ``derivations_pump_control`` from closed forms, never
from the solver.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from opensolve_pipe.models.components import Pump
from opensolve_pipe.models.project import Project
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
    reservoir,
)
from tests.reference.derivations_pumps import DISCHARGE_A, SUCTION_A, curve_a, curve_b
from tests.reference.line import Line

NU = dv.FLUID_A[2] / dv.FLUID_A[1]
RELATIVE = 0.005
FLOW_FLOOR = 1.0e-9


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
