"""Outer loop (design §5): oscillation detection, the iteration cap, correlation-step
averaging of branch K, starved control valves and flow-dependent head offsets."""

import importlib
import math
from typing import Any

import fluids.fittings as ff
import numpy as np
import pytest
from fluids.constants import g

from opensolve_pipe.services.fluids import fluid_properties
from opensolve_pipe.services.solver import solve_project, status
from opensolve_pipe.services.solver.branches import BranchSolution
from opensolve_pipe.services.solver.builder import build_network
from opensolve_pipe.services.solver.elements import HeadOffsetLaw, KTangent
from opensolve_pipe.services.solver.gga import solve_gga
from opensolve_pipe.services.solver.network import NORMAL, LinkMode, LinkState
from opensolve_pipe.services.solver.npsh import npsh_available
from opensolve_pipe.services.solver.status import (
    K_TOL,
    MAX_OUTER_ITERATIONS,
    BranchTracker,
    Status,
    _update_branch,
    initial_branches,
)

from .helpers import connection, make_project, plug, reservoir


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


def check_line() -> Any:
    comps = [reservoir("R1", level=20.0), valve("V", "check"), reservoir("R2", level=10.0)]
    conns = [
        connection("L1", ("R1", "port_1"), ("V", "inlet")),
        connection("L2", ("V", "outlet"), ("R2", "port_1")),
    ]
    return make_project(comps, conns)


def test_oscillating_status_stops_the_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """A rule that flips the check valve on every pass returns to the first solved state:
    converged = false, the valve named in the report, NOT_CONVERGED flagged."""

    def flip(old: Status, dh: float, q: float, h_c: float) -> Status:
        return Status.CLOSED if old is Status.OPEN else Status.OPEN

    monkeypatch.setattr(status, "check_valve_status", flip)
    result = solve_project(check_line())
    assert not result.converged
    assert result.convergence.oscillating_components == ["V"]
    assert result.convergence.outer_iterations == 2
    assert "oscillate" in result.convergence.message
    assert any(f.code == "NOT_CONVERGED" for f in result.flags)
    assert result.node_results == {}


def test_outer_loop_gives_up_after_its_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """A branch whose K never settles (forced here) exhausts the 30 outer iterations."""
    real = status.branch_solution
    calls = {"n": 0}

    def drifting(*args: Any) -> BranchSolution:
        calls["n"] += 1
        solution = real(*args)
        return solution.with_k({p: k + 0.01 * calls["n"] for p, k in solution.k.items()}, g)

    monkeypatch.setattr(status, "branch_solution", drifting)
    comps = [
        reservoir("R1", level=20.0),
        {
            "type": "branch",
            "branchType": "tee",
            "id": "T",
            "name": "T",
            "elevation": 0.0,
            "lossModel": "crane",
            "ports": [{"id": p, "nominalSize": 0.1} for p in ("run_inlet", "run_outlet", "branch")],
        },
        reservoir("R2", level=10.0),
        reservoir("R3", level=12.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("T", "run_inlet")),
        connection("L2", ("T", "run_outlet"), ("R2", "port_1")),
        connection("L3", ("T", "branch"), ("R3", "port_1")),
    ]
    result = solve_project(make_project(comps, conns))
    assert not result.converged
    assert result.convergence.outer_iterations == MAX_OUTER_ITERATIONS
    assert result.convergence.oscillating_components == ["T"]
    assert f"after {MAX_OUTER_ITERATIONS} outer iterations" in result.convergence.message


def wye_built() -> Any:
    """A 45° wye with a small lateral (β² = 0.25 <= 0.35), where K_branch_diverging_Crane
    switches G at q = 0.4 (fluids code: G = 1.1 − 0.7q for q <= 0.4, else 0.85)."""
    comps = [
        reservoir("R1", level=20.0),
        {
            "type": "branch",
            "branchType": "wye",
            "id": "W",
            "name": "W",
            "elevation": 0.0,
            "angle": 45.0,
            "lossModel": "crane",
            "ports": [{"id": p, "nominalSize": 0.1} for p in ("inlet", "outlet_1", "outlet_2")],
        },
        reservoir("R2", level=10.0),
        reservoir("R3", level=10.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("W", "inlet"), diameter=0.1),
        connection("L2", ("W", "outlet_1"), ("R2", "port_1"), diameter=0.1),
        connection("L3", ("W", "outlet_2"), ("R3", "port_1"), diameter=0.05),
    ]
    project = make_project(comps, conns)
    return build_network(project, fluid_properties(project.fluid))


def split_flows(built: Any, q_branch_fraction: float, total: float = 0.02) -> np.ndarray:
    flows = np.zeros(len(built.network.links))
    legs = built.branch_legs["W"]
    flows[legs["inlet"]] = -total  # leg flows run center -> port: inflow is negative
    flows[legs["outlet_2"]] = q_branch_fraction * total
    flows[legs["outlet_1"]] = (1 - q_branch_fraction) * total
    return flows


def test_k_alternating_across_a_correlation_step_is_averaged() -> None:
    built = wye_built()
    tracker: BranchTracker = initial_branches(built)["W"]
    below, above = split_flows(built, 0.4 - 1e-9), split_flows(built, 0.4 + 1e-9)
    k_low = ff.K_branch_diverging_Crane(0.1, 0.05, 0.012, 0.008 - 2e-11, 45.0)
    k_high = ff.K_branch_diverging_Crane(0.1, 0.05, 0.012, 0.008 + 2e-11, 45.0)
    assert abs(k_high - k_low) > K_TOL  # a step, not a slope
    assert _update_branch(built, tracker, below)
    assert _update_branch(built, tracker, above)
    assert not tracker.averaged
    assert _update_branch(built, tracker, below)  # back again: averaged
    assert tracker.averaged
    assert tracker.solution.k["outlet_2"] == pytest.approx(0.5 * (k_low + k_high), rel=1e-6)
    leg = built.network.links[built.branch_legs["W"]["outlet_2"]].law
    assert isinstance(leg, HeadOffsetLaw)
    a_c = math.pi * 0.1**2 / 4
    assert leg.coefficient == pytest.approx(-1 / (2 * g * a_c**2), rel=1e-15)
    assert leg.tangent is not None
    assert leg.tangent.k0 + tracker.solution.k_common == pytest.approx(
        tracker.solution.k["outlet_2"], rel=1e-15
    )
    assert leg.tangent.dk_dq == 0.0  # held constant, no longer a tangent in q
    assert not _update_branch(built, tracker, above)  # held while the pattern lasts


def test_held_k_records_the_two_fluids_values_it_is_the_mean_of() -> None:
    """The held K is the mean of the fluids values at the two splits, both reported (M4 review:
    the trace could not reproduce an averaged K)."""
    built = wye_built()
    tracker = initial_branches(built)["W"]
    for fraction in (0.35, 0.45, 0.35):
        _update_branch(built, tracker, split_flows(built, fraction))
    held = tracker.held_step
    assert held is not None
    assert held.step == 0.4
    assert held.port == "outlet_2"
    assert sorted(held.splits) == pytest.approx([0.35, 0.45], rel=1e-12)
    for q, k in zip(held.splits, held.k_at_splits, strict=True):
        assert k["outlet_2"] == ff.K_branch_diverging_Crane(0.1, 0.05, 1 - q, q, 45.0)
        assert k["outlet_1"] == ff.K_run_diverging_Crane(0.1, 0.05, 1 - q, q, 45.0)
    a, b = held.k_at_splits
    assert tracker.solution.k == pytest.approx({p: 0.5 * (a[p] + b[p]) for p in a}, rel=1e-15)
    # fluids 1.3.1 K_branch_diverging_Crane at angle 45° (< 60: H = 1, J = 2), β² = 0.25:
    # K = G (1 + (q/β²)² − 2 (q/β²) cos 45°), G = 1.1 − 0.7 q up to q = 0.4, 0.85 above.
    bracket = 1 + (0.4 / 0.25) ** 2 - 2 * (0.4 / 0.25) * math.cos(math.radians(45))
    assert held.k_below == pytest.approx((1.1 - 0.7 * 0.4) * bracket, rel=1e-6)
    assert held.k_above == pytest.approx(0.85 * bracket, rel=1e-6)


def test_k_alternating_where_the_correlation_has_no_step_is_not_held() -> None:
    """A tee (90°) with β² = 0.25: neither Crane diverging function steps at q = 0.4, 0.5 or
    0.6 (fluids 1.3.1: G = 1 for angle >= 75° and β² <= 2/3; M = 0.4 for β² <= 0.4), so a split
    alternating across those values is under-relaxed, never held at a mean (M4 review: K held
    30% off the correlation with no step there)."""
    comps = [
        reservoir("R1", level=20.0),
        {
            "type": "branch",
            "branchType": "tee",
            "id": "T",
            "name": "T",
            "elevation": 0.0,
            "lossModel": "crane",
            "ports": [{"id": p, "nominalSize": 0.1} for p in ("run_inlet", "run_outlet", "branch")],
        },
        reservoir("R2", level=10.0),
        reservoir("R3", level=10.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("T", "run_inlet"), diameter=0.1),
        connection("L2", ("T", "run_outlet"), ("R2", "port_1"), diameter=0.1),
        connection("L3", ("T", "branch"), ("R3", "port_1"), diameter=0.05),
    ]
    project = make_project(comps, conns)
    built = build_network(project, fluid_properties(project.fluid))
    legs = built.branch_legs["T"]

    def split(q: float) -> np.ndarray:
        flows = np.zeros(len(built.network.links))
        flows[legs["run_inlet"]], flows[legs["branch"]] = -0.02, q * 0.02
        flows[legs["run_outlet"]] = (1 - q) * 0.02
        return flows

    tracker = initial_branches(built)["T"]
    low, high = split(0.30), split(0.70)
    solution = status._solution_from_flows(built, tracker, low)
    assert status.crane_step(built.branches["T"], solution, 0.3, 0.7) is None
    for flows in (low, high, low, high, low):
        _update_branch(built, tracker, flows)
        assert not tracker.averaged


def test_held_k_is_released_when_the_split_leaves_the_step() -> None:
    """A K held across the step at q = 0.4 returns to the correlation once the solved split
    leaves the two splits the mean was taken between, or the statuses change (M4 review: K held
    at the mean while the split sat at q = 1)."""
    built = wye_built()
    for leave in (
        lambda b: (split_flows(b, 0.9), 3),  # the split moved far from the step
        lambda b: (split_flows(b, 0.38), 1),  # statuses changed before this solve
    ):
        tracker = initial_branches(built)["W"]
        for fraction in (0.35, 0.45, 0.35):
            _update_branch(built, tracker, split_flows(built, fraction))
        assert tracker.averaged
        flows, steady = leave(built)
        assert _update_branch(built, tracker, flows, steady)
        assert not tracker.averaged
        q = tracker.solution.split
        assert q is not None
        assert tracker.solution.k["outlet_2"] == pytest.approx(
            ff.K_branch_diverging_Crane(0.1, 0.05, 1 - q, q, 45.0), rel=1e-12
        )


def test_split_moved_by_status_changes_is_not_held() -> None:
    """A split that returns to where it was two solves ago while statuses changed in between
    was moved by the statuses, not by K across a step: not held."""
    built = wye_built()
    tracker = initial_branches(built)["W"]
    for fraction, steady in ((0.35, 1), (0.45, 1), (0.35, 1)):
        _update_branch(built, tracker, split_flows(built, fraction), steady)
        assert not tracker.averaged


def test_converging_k_is_not_mistaken_for_a_step() -> None:
    """K values that close in on their limit from alternate sides are left to converge."""
    built = wye_built()
    tracker = initial_branches(built)["W"]
    for fraction in (0.30, 0.32, 0.31, 0.3101, 0.31005):
        _update_branch(built, tracker, split_flows(built, fraction))
    assert not tracker.averaged


def test_k_alternating_on_a_smooth_stretch_is_damped_not_held() -> None:
    """A split swinging back and forth with no Crane step between (q = 0.30 and 0.34) is an
    outer-loop oscillation, not a step: the K update is under-relaxed (halfway from the K the
    leg law gave at the solved flows to the correlation's K at the solved split), the
    correlation's slope is kept, and nothing is held or flagged."""
    built = wye_built()
    tracker = initial_branches(built)["W"]
    low, high = split_flows(built, 0.30), split_flows(built, 0.34)
    assert _update_branch(built, tracker, low)
    assert _update_branch(built, tracker, high)
    leg = built.network.links[built.branch_legs["W"]["outlet_2"]].law
    assert isinstance(leg, HeadOffsetLaw)
    used = leg.k(low) + tracker.solution.k_common  # the K the law gives back at q = 0.30
    k_low = ff.K_branch_diverging_Crane(0.1, 0.05, 0.014, 0.006, 45.0)
    assert abs(k_low - used) > K_TOL
    assert _update_branch(built, tracker, low)  # back again: damped
    assert not tracker.averaged
    assert leg.tangent is not None
    assert leg.tangent.q0 == pytest.approx(0.30, rel=1e-12)
    assert leg.tangent.dk_dq != 0.0  # still a tangent in q
    assert leg.tangent.k0 + tracker.solution.k_common == pytest.approx(
        0.5 * (k_low + used), rel=1e-12
    )


def test_fcv_into_a_dead_end_is_starved_and_closed() -> None:
    comps = [reservoir("R1", level=20.0), valve("V", "fcv", setpoint=0.01), plug("X")]
    conns = [
        connection("L1", ("R1", "port_1"), ("V", "inlet")),
        connection("L2", ("V", "outlet"), ("X", "port_1")),
    ]
    project = make_project(comps, conns)
    built = build_network(project, fluid_properties(project.fluid))
    states = [NORMAL] * len(built.network.links)
    k = built.valves["V"].link_index
    states[k] = LinkState(LinkMode.FIXED_FLOW, 0.01)
    gga = solve_gga(built.network, states, tolerance=1e-9, max_iterations=50)
    assert gga.converged
    assert gga.starved_links == [k]
    assert gga.flows[k] == 0.0
    assert np.all(np.abs(gga.flows) <= 1e-15)  # round-off on the dead-end pipe
    result = solve_project(project)
    assert result.converged
    assert all(link.flow == 0.0 for link in result.link_results.values())
    assert "V" not in result.valve_results  # its outlet side has no head
    assert any(f.code == "ISOLATED_SECTION" for f in result.flags)


def test_flow_dependent_head_offset() -> None:
    law = HeadOffsetLaw(0.2, coefficient=-50.0, reference=1)
    flows = np.array([0.0, -0.03, 0.01])
    assert law.head(flows) == pytest.approx(0.2 - 50.0 * (-0.03) * 0.03, rel=1e-15)
    with pytest.raises(ValueError, match="head\\(flows\\)"):
        law.evaluate(0.01)
    law.set(1.5)
    assert law.evaluate(0.01) == (1.5, 0.0)
    assert law.head(flows) == 1.5


def test_npsh_available_is_the_absolute_head_above_vapor_pressure() -> None:
    """NPSHa = p_abs/(ρg) + v²/(2g) − p_vap/(ρg), with p_abs = p_gauge + p_atm and the EGL
    H = z + p_gauge/(ρg) + v²/(2g)."""
    rho, z, p_gauge, v, p_atm, p_vap = 1010.0, 3.0, -2.0e4, 2.5, 9.5e4, 4.2e3
    egl = z + p_gauge / (rho * g) + v * v / (2 * g)
    expected = (p_gauge + p_atm) / (rho * g) + v * v / (2 * g) - p_vap / (rho * g)
    assert npsh_available(egl, z, p_atm, p_vap, rho, g) == pytest.approx(expected, rel=1e-14)


# --------------------------------------------------------------------------- zero-flow bands

LADDER_D = 0.1


def ladder(n: int, dh: float) -> Any:
    """Two mains of n equal Crane tees (0.1 m pipe throughout) joined branch to branch by n
    rungs: main A runs from R_A (30 m) to O_A (0 m), main B from R_B (30 m + dh) to O_B (0 m).
    Nearly balanced, so every rung's flow is near zero."""
    comps: list[dict[str, Any]] = [
        reservoir("RA", level=30.0),
        reservoir("RB", level=30.0 + dh),
        reservoir("OA", level=0.0),
        reservoir("OB", level=0.0),
    ]
    conns = []
    for side in "AB":
        for i in range(n):
            comps.append(
                {
                    "type": "branch",
                    "branchType": "tee",
                    "id": f"{side}{i}",
                    "name": f"{side}{i}",
                    "elevation": 0.0,
                    "lossModel": "crane",
                    "ports": [
                        {"id": p, "nominalSize": 0.1} for p in ("run_inlet", "run_outlet", "branch")
                    ],
                }
            )
        for i in range(n - 1):
            conns.append(
                connection(
                    f"{side}{i}-{i + 1}",
                    (f"{side}{i}", "run_outlet"),
                    (f"{side}{i + 1}", "run_inlet"),
                    length=20.0,
                    diameter=LADDER_D,
                )
            )
        conns.append(
            connection(f"in{side}", (f"R{side}", "port_1"), (f"{side}0", "run_inlet"), length=10.0)
        )
        conns.append(
            connection(
                f"out{side}", (f"{side}{n - 1}", "run_outlet"), (f"O{side}", "port_1"), length=10.0
            )
        )
    for i in range(n):
        conns.append(connection(f"rung{i}", (f"A{i}", "branch"), (f"B{i}", "branch"), length=10.0))
    return make_project(comps, conns, max_iterations=100)


def zero_flow_band(result: Any, tee_id: str) -> tuple[float, float]:
    """The heads a tee's dead branch port can take at zero branch flow, from fluids (Crane
    TP-410): with run flow q entering at run port c_in and leaving at c_out (equal run pipes),
    flow just leaving through the branch (diverging from c_in) gives EGL(c_in) − K_div v²/2g,
    flow just entering (converging to c_out) gives EGL(c_out) + K_conv v²/2g, both K at
    Q_branch = 0."""
    br = result.branch_results[tee_id]
    c_in = next(p for p in ("run_inlet", "run_outlet") if br.port_flows[p] > 0)
    c_out = "run_outlet" if c_in == "run_inlet" else "run_inlet"
    q = br.port_flows[c_in]
    vh = (q / (math.pi * LADDER_D**2 / 4)) ** 2 / (2 * g)
    k_div = ff.K_branch_diverging_Crane(LADDER_D, LADDER_D, q, 0.0, 90.0)
    k_conv = ff.K_branch_converging_Crane(LADDER_D, LADDER_D, q, 0.0, 90.0)
    nodes = result.node_results
    a = nodes[f"{tee_id}:{c_in}"].egl - k_div * vh
    b = nodes[f"{tee_id}:{c_out}"].egl + k_conv * vh
    return min(a, b), max(a, b)


@pytest.mark.parametrize(("n", "dh"), [(3, 1e-4), (3, 0.05), (6, 0.05), (6, 0.3)])
def test_nearly_balanced_ladder_of_crane_tees_converges(n: int, dh: float) -> None:
    """The Crane branch K of an equal tee at zero branch flow is 1.0 diverging and −0.9
    converging, so a rung between two such tees can sit in a band with no flow either way.
    Each rung that ends with no flow is held at both ends together: its one head lies in both
    tees' bands, and it is reported (not an isolated section). Before the pair hold (and the
    signed flow split in the leg law), these ladders cycled or stalled to the iteration cap."""
    result = solve_project(ladder(n, dh))
    assert result.converged, result.convergence.message
    assert not [f for f in result.flags if f.code in ("ISOLATED_SECTION", "NOT_CONVERGED")]
    flows = {cid: lr.flow for cid, lr in result.link_results.items()}
    q_max = max(abs(q) for q in flows.values())
    for side in "AB":
        for i in range(n):
            br = result.branch_results[f"{side}{i}"]
            assert abs(sum(br.port_flows.values())) <= 1e-9 * q_max
    held = 0
    for i in range(n):
        if flows[f"rung{i}"] != 0.0:
            continue
        held += 1
        a, b = result.node_results[f"A{i}:branch"], result.node_results[f"B{i}:branch"]
        assert a.egl == b.egl  # a pipe with no flow loses no head
        for tee_id, node in ((f"A{i}", a), (f"B{i}", b)):
            low, high = zero_flow_band(result, tee_id)
            assert low - status.HTOL <= node.egl <= high + status.HTOL
            assert "carries no flow" in result.branch_results[tee_id].correlation
    assert held > 0


def test_dead_band_of_a_run_leg_has_a_darby_limit() -> None:
    """A tee turning flow from its run inlet into its branch, run outlet held at zero flow.
    Flow just leaving through the run outlet is the Crane diverging pattern at q = 1:
    EGL(run_inlet) − K_run_diverging v_c²/2g. Flow just entering through it makes the branch
    carry the combined flow (Crane has no such pattern): the Darby 3-K run path on the leg's own
    velocity, which vanishes with that flow, so the limit is the branch's EGL. (Without that
    limit the band could not be evaluated, and a held run leg was never re-opened.)"""
    comps = [
        reservoir("R1", level=20.0),
        reservoir("R2", level=10.0),
        reservoir("R3", level=5.0),
        {
            "type": "branch",
            "branchType": "tee",
            "id": "T",
            "name": "T",
            "elevation": 0.0,
            "lossModel": "crane",
            "ports": [{"id": p, "nominalSize": 0.1} for p in ("run_inlet", "run_outlet", "branch")],
        },
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("T", "run_inlet")),
        connection("L2", ("T", "run_outlet"), ("R2", "port_1")),
        connection("L3", ("T", "branch"), ("R3", "port_1"), diameter=0.08),
    ]
    project = make_project(comps, conns)
    built = build_network(project, fluid_properties(project.fluid))
    tracker = initial_branches(built)["T"]
    tracker.dead_leg = "run_outlet"
    legs = built.branch_legs["T"]
    q = 0.012
    flows = np.zeros(len(built.network.links))
    flows[legs["run_inlet"]] = -q  # leg flows run center -> port: inflow is negative
    flows[legs["branch"]] = q
    heads = np.zeros(len(built.network.nodes))
    index = built.network.node_index
    heads[index["T:run_inlet"]], heads[index["T:branch"]] = 18.0, 17.5
    band = status._dead_band(built, tracker, flows, heads)
    assert band is not None
    h_out, h_in = band.h_out, band.h_in
    out_solution = band.solution(built, tracker.geometry, 0)
    in_solution = band.solution(built, tracker.geometry, 1)
    v_c = q / (math.pi * 0.1**2 / 4)
    k_run = ff.K_run_diverging_Crane(0.1, 0.08, 0.0, q, 90.0)
    assert h_out == pytest.approx(18.0 - k_run * v_c**2 / (2 * g), rel=1e-6)
    assert out_solution.model == "crane"
    assert h_in == 17.5
    assert in_solution.model == "darby"


def test_leg_law_follows_its_tangent_through_a_reversed_branch_flow() -> None:
    """Inside one Newton solve the branch flow may cross zero. The leg law's K is the tangent
    line in the signed split q = −Q_own/Q_ref (continuous and monotone through q = 0, held
    inside the correlation's K range), not mirrored about q = 0, which made Newton stall."""
    t = KTangent(k0=-0.5, dk_dq=2.0, q0=0.1, run_path=False, k_min=-0.9, k_max=1.1)
    law = HeadOffsetLaw(0.0, coefficient=-2.0, reference=0)
    law.set(0.0, -2.0, 0, t)
    law.own = 1
    q_ref = 0.02  # combined leg flow (center -> port)
    for q_own, expected in (
        (-0.002, -0.5),  # in the pattern: q = 0.1
        (-0.0002, -0.5 + 2.0 * (0.01 - 0.1)),  # q = 0.01
        (0.0002, -0.5 + 2.0 * (-0.01 - 0.1)),  # reversed: q = −0.01, on the same line
        (0.004, -0.9),  # q = −0.2: held at k_min
    ):
        flows = np.array([q_ref, q_own])
        assert law.k(flows) == pytest.approx(expected, rel=1e-12)
    # d(head)/dQ_own = coefficient · Q_ref|Q_ref| · dK/dq · dq/dQ_own, dq/dQ_own = −1/Q_ref.
    flows = np.array([q_ref, 0.0002])
    assert law.own_slope(flows) == pytest.approx(-2.0 * q_ref * q_ref * 2.0 * (-1 / q_ref))
    assert law.own_slope(np.array([q_ref, 0.004])) == 0.0  # K held at a bound


def crane_ladder(rungs: int) -> Any:
    """A looped ladder (M4 review): a pump feeds rail A, a reservoir feeds rail B, the rails of
    Crane tees are joined by rung pipes and end in reservoirs; carbon steel sch. 40 4" pipe
    with two long-radius elbows per connection (test inputs). Most rungs carry no flow: the
    head across them lies in the band between the Crane values for flow out of and into a
    tee's branch at zero flow."""

    def pipe(cid: str, a: tuple[str, str], b: tuple[str, str]) -> dict[str, Any]:
        steel = {"materialId": "carbon_steel", "schedule": "40", "nominalSize": 0.1016}
        return connection(
            cid,
            a,
            b,
            pipes=[{**steel, "length": 30.0}],
            fittings=[{"type": "elbow_90_lr", "quantity": 2}],
        )

    comps: list[dict[str, Any]] = [
        reservoir("R0", level=5.0),
        {
            "type": "pump",
            "id": "PU",
            "name": "PU",
            "elevation": 0.0,
            "curveId": "C1",
            "ports": [
                {"id": "suction", "nominalSize": 0.1},
                {"id": "discharge", "nominalSize": 0.1},
            ],
        },
        reservoir("RA", level=10.0),
        reservoir("RB", level=12.0),
        reservoir("RBin", level=8.0),
    ]
    conns = [pipe("F", ("R0", "port_1"), ("PU", "suction"))]
    for i in range(rungs):
        for rail in "AB":
            comps.append(
                {
                    "type": "branch",
                    "branchType": "tee",
                    "id": f"T{rail}{i}",
                    "name": f"T{rail}{i}",
                    "elevation": 0.0,
                    "lossModel": "crane",
                    "ports": [
                        {"id": p, "nominalSize": 0.1} for p in ("run_inlet", "run_outlet", "branch")
                    ],
                }
            )
        conns.append(pipe(f"G{i}", (f"TA{i}", "branch"), (f"TB{i}", "branch")))
    conns.append(pipe("FA", ("PU", "discharge"), ("TA0", "run_inlet")))
    conns.append(pipe("SB", ("RBin", "port_1"), ("TB0", "run_inlet")))
    for i in range(rungs - 1):
        conns.append(pipe(f"A{i}", (f"TA{i}", "run_outlet"), (f"TA{i + 1}", "run_inlet")))
        conns.append(pipe(f"B{i}", (f"TB{i}", "run_outlet"), (f"TB{i + 1}", "run_inlet")))
    conns.append(pipe("EA", (f"TA{rungs - 1}", "run_outlet"), ("RA", "port_1")))
    conns.append(pipe("EB", (f"TB{rungs - 1}", "run_outlet"), ("RB", "port_1")))
    curve = {
        "id": "C1",
        "name": "curve",
        "points": [
            {"flow": 0.0, "head": 40.0},
            {"flow": 0.02, "head": 35.0},
            {"flow": 0.04, "head": 20.0},
        ],
    }
    return make_project(comps, conns, pump_library=[curve])


def test_long_crane_ladder_converges_within_the_status_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """In a long ladder the rung legs join the flow reversals a few at a time, so a repeated
    status vector (the global cycle test) came only after ~n/9 outer iterations and a
    505-component ladder hit the 30-iteration cap (M4 review). A leg whose flow reverses back
    is now held at zero flow at once, and iterations that only hold or release such legs (a
    finite active set) are not counted: the counted iterations no longer grow with length.
    Here a 60-rung ladder converges under a cap of 6 counted iterations."""
    monkeypatch.setattr(status, "MAX_OUTER_ITERATIONS", 6)
    project = crane_ladder(60)
    result = solve_project(project)
    assert result.converged, result.convergence.message
    assert result.convergence.outer_iterations > 6  # the uncounted hold iterations
    held = [b for b in result.branch_results.values() if "carries no flow" in b.correlation]
    assert held  # rungs at zero flow inside their bands
    flows = {cid: link.flow for cid, link in result.link_results.items()}
    for comp in project.components:
        if comp.type != "branch":
            continue
        net = sum(
            flows[c.id] * (1 if c.to_component_id == comp.id else -1)
            for c in project.connections
            if comp.id in (c.from_component_id, c.to_component_id)
        )
        assert abs(net) <= 1e-9 * max(abs(q) for q in flows.values())


def test_system_curve_points_continue_from_their_neighbour(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each system-curve point starts from the neighbouring point's solution, so a curve costs
    far fewer Newton iterations than solving each from the initial state (M4 review: /solve with
    the frontend's options took 2.7 s for 19 components, over the PRD's 1 s), and gives the
    same heads where the solution is unique. And the Crane K range Newton holds a tangent to
    is sampled once per geometry."""
    # The package exports a function named system_curve, so the module is fetched by name.
    sc = importlib.import_module("opensolve_pipe.services.solver.system_curve")

    project = crane_ladder(7)
    built = build_network(project, fluid_properties(project.fluid))
    main = status.run_outer_loop(built, tolerance=1e-9, max_iterations=100)
    flows = sc.curve_flows(0.0, sc.default_flow_max(built, "PU"), 15)
    newton = {"n": 0}
    real = sc.run_outer_loop

    def counting(*args: Any, **kwargs: Any) -> Any:
        result = real(*args, **kwargs)
        newton["n"] += result.inner_iterations
        return result

    monkeypatch.setattr(sc, "run_outer_loop", counting)
    points = sc.system_curve_points(
        built, "PU", flows, tolerance=1e-9, max_iterations=100, warm=main
    )
    continued = newton["n"]
    cold = 0
    for q, point in zip(flows, points, strict=True):
        alone = real(built, tolerance=1e-9, max_iterations=100, forced_flows={"PU": q})
        cold += alone.inner_iterations
        assert point.converged
        assert alone.converged
    assert continued < 0.8 * cold
