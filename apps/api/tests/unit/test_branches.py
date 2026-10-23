"""Tee and wye flow patterns and path losses (design §5.4).

Pattern detection is checked for every feasible combination of port-flow signs (in, out,
zero; continuity rules out the others). K values are the cited fluids Crane and Darby
functions, called directly here with the arguments their docstrings define.
"""

import math

import fluids.fittings as ff
import numpy as np
import pytest
from fluids.constants import g

from opensolve_pipe.services.solver.branches import (
    DARBY_TEE,
    BranchGeometry,
    BranchSolution,
    branch_solution,
    flow_pattern,
)
from opensolve_pipe.services.solver.elements import HeadOffsetLaw

NU = 1.0e-6  # m²/s, test input
TEE_PORTS = ("run_inlet", "run_outlet", "branch")
WYE_PORTS = ("inlet", "outlet_1", "outlet_2")


def area(d: float) -> float:
    return math.pi * d * d / 4


def geometry(
    kind: str = "tee", d_run: float = 0.1, d_branch: float = 0.08, d_run2: float | None = None
) -> BranchGeometry:
    ports = TEE_PORTS if kind == "tee" else WYE_PORTS
    run2 = d_run if d_run2 is None else d_run2
    diameters = dict(zip(ports, (d_run, run2, d_branch), strict=True))
    return BranchGeometry(
        component_id="T",
        branch_type="tee" if kind == "tee" else "wye",
        angle=90.0 if kind == "tee" else 45.0,
        run_ports=(ports[0], ports[1]),
        branch_port=ports[2],
        legs={p: i for i, p in enumerate(ports)},
        diameter=diameters,
        area={p: area(d) for p, d in diameters.items()},
    )


# (signs of run_1, run_2, branch inflow) -> (kind, combined port index, model for a tee)
PATTERNS = {
    (0, 0, 0): ("none", None, "none"),
    (1, -1, 0): ("diverging", 0, "crane"),  # dead branch: q = 0
    (-1, 1, 0): ("diverging", 1, "crane"),
    (1, 0, -1): ("diverging", 0, "crane"),  # dead run leg: q = 1 (an elbow via the branch)
    (0, 1, -1): ("diverging", 1, "crane"),
    (-1, 0, 1): ("converging", 0, "crane"),  # branch -> run_1, run_2 dead: q = 1
    (0, -1, 1): ("converging", 1, "crane"),
    (1, -1, -1): ("diverging", 0, "crane"),
    (-1, 1, -1): ("diverging", 1, "crane"),
    (-1, -1, 1): ("diverging", 2, "darby"),  # combined flow in through the branch
    (-1, 1, 1): ("converging", 0, "crane"),
    (1, -1, 1): ("converging", 1, "crane"),
    (1, 1, -1): ("converging", 2, "darby"),  # both runs into the branch
}


def inflows(signs: tuple[int, int, int], ports: tuple[str, str, str]) -> dict[str, float]:
    """Port inflows with the given signs that satisfy continuity (they sum to zero): inflow
    ports carry 0.007 and 0.013 m³/s, outflow ports split the total 35 % / 65 %."""
    ins = [p for p, s in zip(ports, signs, strict=True) if s > 0]
    outs = [p for p, s in zip(ports, signs, strict=True) if s < 0]
    q = dict.fromkeys(ports, 0.0)
    for port, value in zip(ins, (0.007, 0.013) if len(ins) == 2 else (0.02,), strict=False):
        q[port] = value
    total = sum(q.values())
    for port, share in zip(outs, (0.35, 0.65) if len(outs) == 2 else (1.0,), strict=False):
        q[port] = -share * total
    assert abs(sum(q.values())) < 1e-15
    return q


@pytest.mark.parametrize("kind", ["tee", "wye"])
@pytest.mark.parametrize("signs", sorted(PATTERNS))
def test_flow_pattern_for_every_sign_combination(kind: str, signs: tuple[int, int, int]) -> None:
    ports = TEE_PORTS if kind == "tee" else WYE_PORTS
    q = inflows(signs, ports)
    expected_kind, index, model = PATTERNS[signs]
    combined = None if index is None else ports[index]
    assert flow_pattern(geometry(kind), q) == (expected_kind, combined)
    solution = branch_solution(geometry(kind), q, NU, g)
    if kind == "wye" and model == "darby":
        model = "unsupported"
    assert solution.model == model
    assert solution.combined == combined
    if combined is None:
        assert solution.pattern == "no flow"
    else:
        word = "from" if expected_kind == "diverging" else "to"
        assert solution.pattern == f"{expected_kind} {word} {combined}"


def test_solver_noise_on_a_dead_leg_does_not_flip_the_pattern() -> None:
    for noise in (1e-17, -1e-17, 3e-13, -3e-13):
        q = {"run_inlet": 0.02, "run_outlet": -0.02 - noise, "branch": noise}
        assert flow_pattern(geometry(), q) == ("diverging", "run_inlet")


def leg_law(sol: BranchSolution, geo: BranchGeometry, port: str) -> HeadOffsetLaw:
    """The leg's offset law as the outer loop sets it (the combined leg's may be None: 0)."""
    spec = sol.combined_leg if port == sol.combined else sol.legs[port]
    law = HeadOffsetLaw()
    law.own = geo.legs[port]
    if spec is not None:
        law.set(0.0, spec.coefficient, spec.reference, spec.tangent)
    return law


def path_drop(sol: BranchSolution, geo: BranchGeometry, port: str, flows: np.ndarray) -> float:
    """H_combined − H_port from the leg laws (H_center − H_p = offset_p on each leg)."""
    assert sol.combined is not None
    return leg_law(sol, geo, port).head(flows) - leg_law(sol, geo, sol.combined).head(flows)


def leg_flows(geo: BranchGeometry, inflow: dict[str, float]) -> np.ndarray:
    """Leg flows (center -> port) from port inflows."""
    flows = np.zeros(3)
    for port, leg in geo.legs.items():
        flows[leg] = -inflow[port]
    return flows


@pytest.mark.parametrize("kind", ["tee", "wye"])
@pytest.mark.parametrize("combined", [0, 1])
def test_diverging_k_and_offsets_are_crane(kind: str, combined: int) -> None:
    """K_branch/run_diverging_Crane(D_run, D_branch, Q_run_out, Q_branch_out, angle); path
    losses K v_c²/(2g) with v_c on D_run, on the non-combined legs."""
    ports = TEE_PORTS if kind == "tee" else WYE_PORTS
    c, r, b = ports[combined], ports[1 - combined], ports[2]
    geo = geometry(kind)
    q_run, q_branch = 0.013, 0.007
    q = {c: q_run + q_branch, r: -q_run, b: -q_branch}
    sol = branch_solution(geo, q, NU, g)
    angle = geo.angle
    k_b = ff.K_branch_diverging_Crane(0.1, 0.08, q_run, q_branch, angle)
    k_r = ff.K_run_diverging_Crane(0.1, 0.08, q_run, q_branch, angle)
    assert sol.k == {b: k_b, r: k_r}
    assert sol.range_notes == reversed_lateral_notes(kind, c)
    # Offsets: H_center − H_port = K v_c²/(2g) in the flow direction (center -> port).
    flows = leg_flows(geo, q)
    v_c = (q_run + q_branch) / area(0.1)
    for port, k in ((b, k_b), (r, k_r)):
        assert path_drop(sol, geo, port, flows) == pytest.approx(k * v_c**2 / (2 * g), rel=1e-13)
    assert c not in sol.legs


def reversed_lateral_notes(kind: str, combined: str) -> list[str]:
    """The range note expected for a wye whose combined flow passes through outlet_1: its
    lateral leans toward outlet_1, so the lateral flow turns 180° − 45° = 135°, outside the
    Crane lateral data (which have the branch meet the combined flow at the wye's angle)."""
    if kind == "wye" and combined == "outlet_1":
        return [
            "the combined flow passes through outlet_1, toward which the lateral leans, so the "
            "lateral's flow turns 135° instead of 45°; the Crane lateral data cover a branch "
            "meeting the combined flow at the wye's angle (K evaluated at 45°, likely an "
            "underestimate)"
        ]
    return []


@pytest.mark.parametrize("kind", ["tee", "wye"])
@pytest.mark.parametrize("combined", [0, 1])
def test_converging_k_and_offsets_are_crane(kind: str, combined: int) -> None:
    ports = TEE_PORTS if kind == "tee" else WYE_PORTS
    c, r, b = ports[combined], ports[1 - combined], ports[2]
    geo = geometry(kind)
    q_run, q_branch = 0.011, 0.004
    q = {c: -(q_run + q_branch), r: q_run, b: q_branch}
    sol = branch_solution(geo, q, NU, g)
    k_b = ff.K_branch_converging_Crane(0.1, 0.08, q_run, q_branch, geo.angle)
    k_r = ff.K_run_converging_Crane(0.1, 0.08, q_run, q_branch, geo.angle)
    assert sol.k == {b: k_b, r: k_r}
    assert sol.range_notes == reversed_lateral_notes(kind, c)
    flows = leg_flows(geo, q)
    v_c = (q_run + q_branch) / area(0.1)
    for port, k in ((b, k_b), (r, k_r)):
        # Converging: the loss runs port -> center, so H_center − H_port = −K v_c²/(2g).
        assert path_drop(sol, geo, port, flows) == pytest.approx(-k * v_c**2 / (2 * g), rel=1e-13)


CRANE = {
    ("diverging", "branch"): ff.K_branch_diverging_Crane,
    ("diverging", "run"): ff.K_run_diverging_Crane,
    ("converging", "branch"): ff.K_branch_converging_Crane,
    ("converging", "run"): ff.K_run_converging_Crane,
}


@pytest.mark.parametrize("kind", ["diverging", "converging"])
@pytest.mark.parametrize("path", ["branch", "run"])
def test_leg_offsets_follow_the_split_and_their_own_slope(kind: str, path: str) -> None:
    """Moving flow between the run and the branch at a fixed combined flow: the leg offset
    tracks K(q) v_c²/(2g) from the fluids function to first order, and its own-flow slope
    (the Jacobian term) matches a central difference of that exact offset."""
    geo = geometry()
    total, d_run, d_branch = 0.02, 0.1, 0.08
    s = -1.0 if kind == "diverging" else 1.0  # sign of a non-combined port's inflow
    port = "branch" if path == "branch" else "run_outlet"
    combined = "run_inlet"
    function = CRANE[(kind, path)]

    def inflow(q_branch: float) -> dict[str, float]:
        return {combined: -s * total, "run_outlet": s * (total - q_branch), "branch": s * q_branch}

    def exact(q_branch: float) -> float:  # H_center − H_port from the Crane function
        k = function(d_run, d_branch, total - q_branch, q_branch, 90.0)
        return -s * k * (total / area(d_run)) ** 2 / (2 * g)

    q0 = 0.0062
    sol = branch_solution(geo, inflow(q0), NU, g)
    law = leg_law(sol, geo, port)
    flows0 = leg_flows(geo, inflow(q0))
    assert path_drop(sol, geo, port, flows0) == pytest.approx(exact(q0), rel=1e-13)
    step = 1e-7
    for dq in (-step, step):
        moved = leg_flows(geo, inflow(q0 + dq))
        assert path_drop(sol, geo, port, moved) == pytest.approx(exact(q0 + dq), rel=1e-9)
    # d(offset)/dQ_own: the own leg's flow is the branch flow or the run flow.
    own_sign = 1.0 if path == "branch" else -1.0  # dQ_branch = ±dQ_own
    numeric = (exact(q0 + step) - exact(q0 - step)) / (2 * step)
    leg_own_flow_per_branch_flow = -s * own_sign  # d(leg flow)/d(Q_branch)
    assert law.own_slope(flows0) == pytest.approx(numeric / leg_own_flow_per_branch_flow, rel=1e-4)


def test_dead_branch_gets_the_crane_k_at_zero_branch_flow() -> None:
    q = {"run_inlet": 0.02, "run_outlet": -0.02, "branch": 0.0}
    sol = branch_solution(geometry(), q, NU, g)
    assert sol.k["branch"] == ff.K_branch_diverging_Crane(0.1, 0.08, 0.02, 0.0, 90.0)
    assert sol.k["run_outlet"] == ff.K_run_diverging_Crane(0.1, 0.08, 0.02, 0.0, 90.0)


@pytest.mark.parametrize("sign", [1.0, -1.0])
def test_tee_fallback_uses_darby_on_each_run_legs_own_velocity(sign: float) -> None:
    """Combined flow through the branch: K_x = Darby3K(Di=D_x, Re=Re_x, name=...)."""
    geo = geometry(d_run=0.1, d_run2=0.09)
    q = {"run_inlet": -sign * 0.006, "run_outlet": -sign * 0.009, "branch": sign * 0.015}
    sol = branch_solution(geo, q, NU, g)
    assert sol.model == "darby"
    assert sol.combined == "branch"
    flows = np.zeros(3)
    for port, leg in geo.legs.items():
        flows[leg] = -q[port]
    for port in ("run_inlet", "run_outlet"):
        d = geo.diameter[port]
        re = abs(q[port]) * d / (area(d) * NU)
        k = ff.Darby3K(Di=d, Re=re, name=DARBY_TEE)
        assert sol.k[port] == k
        assert sol.legs[port].reference == geo.legs[port]
        assert sol.legs[port].tangent is None
        v = q[port] / area(d)
        law = leg_law(sol, geo, port)
        # Diverging from the branch: a head drop center -> port; converging: port -> center.
        assert law.head(flows) == pytest.approx(sign * k * v * v / (2 * g), rel=1e-13)
        # The leg's loss grows with its own flow: slope 2 K |Q|/(2 g A²).
        assert law.own_slope(flows) == pytest.approx(
            2 * k * abs(q[port]) / (2 * g * area(d) ** 2), rel=1e-13
        )


def test_wye_with_combined_flow_through_its_lateral_is_unsupported() -> None:
    q = {"inlet": -0.006, "outlet_1": -0.009, "outlet_2": 0.015}
    sol = branch_solution(geometry("wye"), q, NU, g)
    assert sol.model == "unsupported"
    assert sol.legs == {}
    assert "no cited correlation" in sol.correlation


def test_range_notes_for_a_large_branch_and_unequal_runs() -> None:
    q = {"run_inlet": 0.02, "run_outlet": -0.012, "branch": -0.008}
    sol = branch_solution(geometry(d_run=0.1, d_branch=0.12, d_run2=0.09), q, NU, g)
    assert len(sol.range_notes) == 2
    assert "β > 1" in sol.range_notes[0]
    assert "equal run diameters" in sol.range_notes[1]
    assert branch_solution(geometry(), q, NU, g).range_notes == []


def test_with_k_holds_constant_k_values() -> None:
    geo = geometry()
    q = {"run_inlet": 0.02, "run_outlet": -0.012, "branch": -0.008}
    sol = branch_solution(geo, q, NU, g)
    other = sol.with_k({"branch": 0.5, "run_outlet": 0.0}, g)
    assert other.pattern == sol.pattern
    assert sol.k_common == 0.0 or other.k_common == sol.k_common
    flows = leg_flows(geo, q)
    v_c = 0.02 / area(0.1)
    moved = leg_flows(geo, {"run_inlet": 0.02, "run_outlet": -0.011, "branch": -0.009})
    for port, k in (("branch", 0.5), ("run_outlet", 0.0)):
        law = leg_law(other, geo, port)
        assert path_drop(other, geo, port, flows) == pytest.approx(
            k * v_c**2 / (2 * g), rel=1e-12, abs=1e-15
        )
        assert law.k(moved) == law.k(flows)  # no longer follows the split
        assert law.own_slope(flows) == 0.0
