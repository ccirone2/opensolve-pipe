"""The NOT_CONVERGED flag's residual locations (method 1.2.0; proposal
vfd-slice2-discharge-pressure.md §2.11.10, fix (a), the owner's answer Q9 (a) of 2026-10-24).

The flag names where a continuity residual (``maxContinuityResidualAt``) or an energy residual
(``maxEnergyResidualAt``) lies only where that residual exceeds its stop tolerance: a location
of residuals within it, or exactly 0 (where the largest is the first node or link), says
nothing about why the solve failed. Where the status rules keep returning to a state whose
solve failed, the result reports the residuals of that solve, which its message describes.

Every expected location is derived in the test: from the reported flows (continuity), from
the Darcy–Weisbach law written out with fluids' Colebrook (energy), or from the topology (a
network whose only link is one pipe).
"""

import math
import re
from typing import Any

import pytest
from fluids.constants import g
from fluids.friction import Colebrook

from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import Flag, SolvedState
from opensolve_pipe.services.fluids import fluid_properties
from opensolve_pipe.services.solver import solve_project, status
from opensolve_pipe.services.solver.builder import build_network
from opensolve_pipe.services.solver.gga import GgaResult, solve_gga
from opensolve_pipe.services.solver.network import NORMAL, LinkMode, LinkState, SolverNetwork
from opensolve_pipe.services.solver.results import build_solved_state
from opensolve_pipe.services.solver.status import OuterLoopResult, Status

from .helpers import connection, custom_fluid, make_project, reservoir, tee

RHO, MU = 998.0, 1.0e-3  # test inputs (custom fluid)
ENERGY_TOL = 1.0e-7  # m, the energy stop tolerance at heads where round-off is negligible
CONTINUITY_ATOL = 1.0e-14  # m³/s, the continuity tolerance's absolute floor


def valve(cid: str, vtype: str, **kw: Any) -> dict[str, Any]:
    return {
        "type": "valve",
        "valveType": vtype,
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "ports": [{"id": "inlet", "nominalSize": 0.1}, {"id": "outlet", "nominalSize": 0.1}],
        **kw,
    }


def not_converged_flag(result: SolvedState) -> Flag:
    assert not result.converged
    [flag] = [f for f in result.flags if f.code == "NOT_CONVERGED"]
    return flag


def flipping_check_valve(monkeypatch: pytest.MonkeyPatch) -> None:
    """A check-valve rule that flips on every pass: the outer loop returns to the first state
    and stops, every inner solve having converged."""

    def flip(old: Status, dh: float, q: float, h_c: float) -> Status:
        return Status.CLOSED if old is Status.OPEN else Status.OPEN

    monkeypatch.setattr(status, "check_valve_status", flip)


def check_line() -> Project:
    """R1 (20 m) -> L1 -> check valve V -> L2 -> R2 (10 m)."""
    comps = [reservoir("R1", level=20.0), valve("V", "check"), reservoir("R2", level=10.0)]
    conns = [
        connection("L1", ("R1", "port_1"), ("V", "inlet")),
        connection("L2", ("V", "outlet"), ("R2", "port_1")),
    ]
    return make_project(comps, conns)


def check_branch() -> Project:
    """R1 (20 m) -> L1 -> ideal tee T1 -> L2 -> check valve V -> L3 -> R2 (10 m), and the tee's
    branch -> L4 -> R3 (5 m). The tee's ports share one head, so the continuity residuals at
    them come out exactly 0."""
    comps = [
        reservoir("R1", level=20.0),
        tee("T1"),
        valve("V", "check"),
        reservoir("R2", level=10.0),
        reservoir("R3", level=5.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("T1", "run_inlet")),
        connection("L2", ("T1", "run_outlet"), ("V", "inlet")),
        connection("L3", ("V", "outlet"), ("R2", "port_1")),
        connection("L4", ("T1", "branch"), ("R3", "port_1")),
    ]
    return make_project(comps, conns)


@pytest.mark.parametrize("project", [check_line, check_branch])
def test_the_flag_names_no_location_when_every_residual_is_within_tolerance(
    monkeypatch: pytest.MonkeyPatch, project: Any
) -> None:
    """Statuses that oscillate end the loop after inner solves that all converged: no residual
    exceeds its tolerance, so the flag names no residual location (1.1.0 named the node and
    link of the largest round-off residual: V:inlet and L1 at 3.5e-18 m³/s and 1.4e-17 m on
    the line, and T1:run_inlet, the first node, at a continuity residual of exactly 0 on the
    branch). The convergence report still gives the largest residuals and where they lie."""
    flipping_check_valve(monkeypatch)
    result = solve_project(project())
    flag = not_converged_flag(result)
    report = result.convergence
    assert "statuses oscillate" in report.message
    # Within tolerance: below the continuity tolerance's absolute floor and below ENERGY_TOL.
    assert report.max_continuity_residual.value is not None
    assert report.max_continuity_residual.value <= CONTINUITY_ATOL
    assert report.max_energy_residual.value is not None
    assert report.max_energy_residual.value <= ENERGY_TOL
    assert report.max_continuity_residual.element_id is not None
    assert report.max_energy_residual.element_id is not None
    assert flag.details == {"componentIds": "V"}


def series_gate_valve() -> Project:
    """R1 (20 m) -> L1 (0.1 m bore) -> gate valve V -> L2 (0.2 m bore) -> R2 (10 m)."""
    comps = [reservoir("R1", level=20.0), valve("V", "gate"), reservoir("R2", level=10.0)]
    conns = [
        connection("L1", ("R1", "port_1"), ("V", "inlet"), diameter=0.1),
        connection("L2", ("V", "outlet"), ("R2", "port_1"), diameter=0.2),
    ]
    return make_project(comps, conns, fluid=custom_fluid(RHO, MU))


def inner_solve(
    project: Project, max_iterations: int
) -> tuple[SolverNetwork, list[LinkState], GgaResult, SolvedState]:
    """One inner solve stopped at ``max_iterations``, reported as the solve's result."""
    built = build_network(project, fluid_properties(project.fluid))
    states = [NORMAL] * len(built.network.links)
    res = solve_gga(built.network, states, tolerance=1e-9, max_iterations=max_iterations)
    assert not res.converged
    outer = OuterLoopResult(res, states, 1, res.iterations, False, [], res.message)
    return built.network, states, res, build_solved_state(built, outer, 101325.0, "test")


def port_balances(network: SolverNetwork, flows: Any) -> dict[str, float]:
    """Inflow − outflow at each valve port, from the reported flows (no demands here)."""
    balance = {"V:inlet": 0.0, "V:outlet": 0.0}
    for link in network.links:
        for node, sign in ((link.start, -1.0), (link.end, 1.0)):
            key = network.nodes[node].key
            if key in balance:
                balance[key] += sign * float(flows[link.index])
    return balance


def test_the_flag_names_the_node_whose_continuity_residual_exceeds_its_tolerance() -> None:
    """At the starting iterate (no Newton step) the connections carry 1 ft/s each, so the flow
    into V:outlet from the valve (0.1 m size) differs from the flow out through L2 (0.2 m
    bore); V:inlet balances exactly. The flag names V:outlet."""
    network, _, res, state = inner_solve(series_gate_valve(), 0)
    balance = port_balances(network, res.flows)
    q_max = max(abs(float(q)) for q in res.flows)
    tolerance = 1.0e-9 * q_max + CONTINUITY_ATOL
    assert balance["V:inlet"] == 0.0
    assert abs(balance["V:outlet"]) > tolerance
    details = not_converged_flag(state).details
    assert details["maxContinuityResidualAt"] == "V:outlet"
    assert "maxEnergyResidualAt" in details  # 19.9 m at this iterate (the message)


def test_the_flag_names_no_node_once_continuity_closes_after_a_newton_step() -> None:
    """After one Newton step continuity closes to round-off at both valve ports (the step is
    linear in the flows), while the energy equation does not: the flag names the link with the
    largest energy residual and no node (1.1.0 named V:outlet as well)."""
    network, _, res, state = inner_solve(series_gate_valve(), 1)
    balance = port_balances(network, res.flows)
    assert max(abs(b) for b in balance.values()) <= CONTINUITY_ATOL
    details = not_converged_flag(state).details
    assert "maxContinuityResidualAt" not in details
    report = state.convergence
    assert report.max_energy_residual.value is not None
    assert report.max_energy_residual.value > ENERGY_TOL
    assert details["maxEnergyResidualAt"] == report.max_energy_residual.element_id


def test_the_flag_names_the_only_link_when_its_energy_residual_exceeds_its_tolerance() -> None:
    """R1 (20 m) -> P1 -> R2 (10 m) has no free node and one link: after one Newton step from
    1 ft/s the residual h(Q) − 10 m, written out with fluids' Colebrook, exceeds ENERGY_TOL
    plus its round-off allowance (4ε × 20 m), so the flag names P1 and no node."""
    comps = [reservoir("R1", level=20.0), reservoir("R2", level=10.0)]
    conns = [connection("P1", ("R1", "port_1"), ("R2", "port_1"), length=100.0, diameter=0.1)]
    _, _, res, state = inner_solve(make_project(comps, conns, fluid=custom_fluid(RHO, MU)), 1)
    [q] = [float(x) for x in res.flows]
    area = math.pi * 0.1**2 / 4
    v = q / area
    re_number = abs(v) * 0.1 * RHO / MU
    head = Colebrook(re_number, 4.5e-5 / 0.1) * 100.0 / 0.1 * v * abs(v) / (2 * g)
    assert abs(head - 10.0) > ENERGY_TOL + 4 * 2.0**-52 * 20.0
    details = not_converged_flag(state).details
    assert details == {"maxEnergyResidualAt": "P1"}


def test_the_failed_state_exit_reports_the_residuals_its_message_describes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A PRV whose active-state solve fails (here: stopped after one Newton iteration) is
    opened and solved, made active again by its rule, closed and solved, and made active
    again: the loop keeps returning to the failed state and stops. Its message describes the
    failed solve, so the convergence report and the flag give that solve's residuals; 1.1.0
    gave those of the last solve (the PRV closed: 0 m³/s and 0 m, at V:inlet and L1)."""
    real = status.solve_gga

    def failing_when_active(
        network: SolverNetwork, states: list[LinkState], **kw: Any
    ) -> GgaResult:
        if any(s.mode is LinkMode.FIXED_DOWNSTREAM_HEAD for s in states):
            kw["max_iterations"] = 1
        return real(network, states, **kw)

    monkeypatch.setattr(status, "solve_gga", failing_when_active)
    comps = [
        reservoir("R1", level=50.0),
        valve("V", "prv", setpoint=15.0 * RHO * g),
        reservoir("R2", level=5.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("V", "inlet")),
        connection("L2", ("V", "outlet"), ("R2", "port_1")),
    ]
    result = solve_project(make_project(comps, conns, fluid=custom_fluid(RHO, MU)))
    flag = not_converged_flag(result)
    report = result.convergence
    assert "keep returning to this state" in report.message
    found = re.search(
        r"not converged after 1 iterations \(largest flow change [^,]+, continuity residual "
        r"(\S+) m³/s, energy residual (\S+) m\)",
        report.message,
    )
    assert found is not None
    assert report.max_continuity_residual.value is not None
    assert report.max_energy_residual.value is not None
    assert f"{report.max_continuity_residual.value:.3g}" == found.group(1)
    assert f"{report.max_energy_residual.value:.3g}" == found.group(2)
    assert report.max_energy_residual.value > ENERGY_TOL
    assert flag.details["maxEnergyResidualAt"] == report.max_energy_residual.element_id
    # The failed solve's continuity residual is round-off (the Newton step is linear in it).
    assert report.max_continuity_residual.value <= CONTINUITY_ATOL
    assert "maxContinuityResidualAt" not in flag.details


def test_the_flag_names_the_link_where_the_iteration_diverged() -> None:
    """R1 (5 m, 1e8 Pa on its surface) -> P1 -> pump PU1 -> P2 -> R2 (20 m) in a liquid of
    1e-300 kg/m³ and 1e-300 Pa·s (the project of test_api_robustness's diverged-residual test):
    R1's head, 1e8 Pa / (1e-300 kg/m³ × g) ≈ 1e307 m, is near the largest double, and the
    iteration overflows. On a link whose heads or loss are infinite the stop tolerance is
    infinite too, yet a residual that is not finite exceeds any tolerance: the flag names the
    link of the largest energy residual, the one the convergence report names with a null value
    (not finite). The first build of 1.2.0 skipped the infinite residuals and named PU1, whose
    residual is finite, while the report named P1."""
    pump = {
        "type": "pump",
        "id": "PU1",
        "name": "PU1",
        "elevation": 0.0,
        "curveId": "C1",
        "ports": [{"id": "suction", "nominalSize": 0.1}, {"id": "discharge", "nominalSize": 0.1}],
    }
    curve = {
        "id": "C1",
        "name": "curve",
        "points": [
            {"flow": 0.0, "head": 40.0},
            {"flow": 0.02, "head": 35.0},
            {"flow": 0.04, "head": 20.0},
        ],
    }
    comps = [
        reservoir("R1", level=5.0, surface_pressure=1.0e8),
        pump,
        reservoir("R2", level=20.0),
    ]
    conns = [
        connection("P1", ("R1", "port_1"), ("PU1", "suction"), length=10.0),
        connection("P2", ("PU1", "discharge"), ("R2", "port_1"), length=50.0),
    ]
    fluid = custom_fluid(1.0e-300, 1.0e-300, vapor_pressure=1.0e8)
    result = solve_project(make_project(comps, conns, fluid=fluid, pump_library=[curve]))
    flag = not_converged_flag(result)
    report = result.convergence
    assert "the iteration diverged" in report.message
    assert report.max_energy_residual.value is None  # not finite: JSON has no inf
    assert report.max_energy_residual.element_id is not None
    assert flag.details["maxEnergyResidualAt"] == report.max_energy_residual.element_id
