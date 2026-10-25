"""GGA on small networks, with expectations derived in the test (fluids Colebrook + brentq).

Never computed with solver code: every expected flow is a root of the Darcy–Weisbach energy
equation written out below with ``fluids.friction.Colebrook`` and fluids fitting functions.
"""

import math
import random

import numpy as np
import pytest
from fluids.constants import g
from fluids.fittings import entrance_sharp, exit_normal
from fluids.friction import Colebrook
from scipy.optimize import brentq

from opensolve_pipe.models.project import Project
from opensolve_pipe.services.fluids import fluid_properties
from opensolve_pipe.services.solver import solve_project
from opensolve_pipe.services.solver.builder import CENTER_PORT, build_network, node_key
from opensolve_pipe.services.solver.elements import HeadOffsetLaw
from opensolve_pipe.services.solver.gga import (
    CONTINUITY_ATOL,
    CONTINUITY_RTOL,
    JACOBIAN_FLOOR_ABSOLUTE,
    JACOBIAN_FLOOR_RELATIVE,
    jacobian_slopes,
    merge_offset_links,
    solve_gga,
)
from opensolve_pipe.services.solver.network import CLOSED, NORMAL, LinkKind
from opensolve_pipe.services.solver.results import build_solved_state
from opensolve_pipe.services.solver.status import OuterLoopResult, run_outer_loop

from .helpers import (
    connection,
    custom_fluid,
    make_project,
    plug,
    reference_node,
    reservoir,
    tee,
    two_reservoirs,
)
from .test_friction import epanet_at_reynolds

RHO, MU = 998.0, 1.0e-3  # test inputs (custom fluid)
NU = MU / RHO


def area(d: float) -> float:
    return math.pi * d * d / 4


def dw_head(q: float, length: float, d: float, eps: float, k: float = 0.0) -> float:
    """Darcy–Weisbach + minor losses for q > 0 in turbulent flow, fluids Colebrook."""
    re = 4 * q / (math.pi * d * NU)
    v = q / area(d)
    return (Colebrook(re, eps / d) * length / d + k) * v * v / (2 * g)


def test_reservoir_pipe_reservoir_closed_form() -> None:
    k = entrance_sharp(method="Crane") + exit_normal()
    comps, conns = two_reservoirs(
        h1=20.0,
        h2=10.0,
        length=100.0,
        diameter=0.1,
        roughness=4.5e-5,
        fittings=[{"type": "entrance_sharp"}, {"type": "exit"}],
    )
    result = solve_project(make_project(comps, conns, fluid=custom_fluid(RHO, MU)))
    expected = brentq(lambda q: dw_head(q, 100.0, 0.1, 4.5e-5, k) - 10.0, 1e-6, 1.0, xtol=1e-15)
    assert result.converged
    assert result.link_results["P1"].flow == pytest.approx(expected, rel=1e-9)
    assert result.link_results["P1"].head_loss == pytest.approx(10.0, abs=1e-9)
    assert result.node_results["R1:port_1"].egl == 20.0
    assert result.node_results["R2:port_1"].egl == 10.0
    assert result.boundary_results["R1"].outflow == pytest.approx(expected, rel=1e-9)
    assert result.boundary_results["R2"].outflow == pytest.approx(-expected, rel=1e-9)
    assert result.convergence.inner_iterations < 20


def test_laminar_pipe_closed_form() -> None:
    """Hagen–Poiseuille: Q = ΔH g π D⁴ / (128 ν L)."""
    mu = 0.5  # a viscous oil, test input
    comps, conns = two_reservoirs(h1=2.0, h2=1.0, length=10.0, diameter=0.02, roughness=0.0)
    result = solve_project(make_project(comps, conns, fluid=custom_fluid(900.0, mu)))
    expected = 1.0 * g * math.pi * 0.02**4 / (128 * (mu / 900.0) * 10.0)
    assert result.link_results["P1"].flow == pytest.approx(expected, rel=1e-12)
    assert result.link_results["P1"].flow_regime == "laminar"


def test_swamee_jain_mode_uses_the_epanet_friction_factor() -> None:
    comps, conns = two_reservoirs(h1=15.0, h2=10.0, length=200.0, diameter=0.15, roughness=1e-4)
    project = make_project(comps, conns, fluid=custom_fluid(RHO, MU), method="swamee_jain")

    def head(q: float) -> float:
        re = 4 * q / (math.pi * 0.15 * NU)
        return (
            epanet_at_reynolds(re, 1e-4 / 0.15)[0] * 200.0 / 0.15 * (q / area(0.15)) ** 2 / (2 * g)
        )

    expected = brentq(lambda q: head(q) - 5.0, 1e-6, 1.0, xtol=1e-15)
    assert solve_project(project).link_results["P1"].flow == pytest.approx(expected, rel=1e-9)


def test_equal_heads_give_zero_flow() -> None:
    comps, conns = two_reservoirs(h1=10.0, h2=10.0)
    result = solve_project(make_project(comps, conns))
    assert result.converged
    assert result.link_results["P1"].flow == 0.0
    assert result.link_results["P1"].flow_regime == "none"


def dead_end_project() -> Project:
    """R1 -> P1 -> T1 (ideal) -> P2 -> R2, with T1's branch -> P3 -> plug X1 (elevated)."""
    comps = [
        reservoir("R1", level=20.0),
        tee("T1"),
        reservoir("R2", level=10.0),
        plug("X1", elevation=5.0),
    ]
    conns = [
        connection("P1", ("R1", "port_1"), ("T1", "run_inlet"), length=60.0),
        connection("P2", ("T1", "run_outlet"), ("R2", "port_1"), length=40.0),
        connection("P3", ("T1", "branch"), ("X1", "port_1"), length=25.0, diameter=0.05),
    ]
    return make_project(comps, conns, fluid=custom_fluid(RHO, MU))


def series_flow(
    dh: float, lengths: tuple[float, ...], d: float = 0.1, eps: float = 4.5e-5
) -> float:
    return float(
        brentq(lambda q: sum(dw_head(q, ln, d, eps) for ln in lengths) - dh, 1e-6, 1.0, xtol=1e-15)
    )


def test_dead_end_branch_has_zero_flow_and_equal_egl() -> None:
    result = solve_project(dead_end_project())
    assert result.converged
    links, nodes = result.link_results, result.node_results
    assert links["P3"].flow == 0.0
    expected = series_flow(10.0, (60.0, 40.0))
    assert links["P1"].flow == pytest.approx(expected, rel=1e-9)
    assert links["P2"].flow == pytest.approx(expected, rel=1e-9)
    h_tee = nodes["T1:run_inlet"].egl
    assert nodes["T1:run_outlet"].egl == pytest.approx(h_tee, abs=1e-9)
    assert nodes["T1:branch"].egl == pytest.approx(h_tee, abs=1e-9)
    assert nodes["X1:port_1"].egl == pytest.approx(h_tee, abs=1e-9)
    assert nodes["X1:port_1"].velocity == 0.0
    plug_node = nodes["X1:port_1"]
    assert plug_node.pressure == pytest.approx(RHO * g * (plug_node.egl - 5.0), rel=1e-12)
    assert result.boundary_results["X1"].outflow == 0.0
    branch = result.branch_results["T1"]
    assert branch.port_flows["branch"] == 0.0
    assert branch.port_flows["run_inlet"] == pytest.approx(expected, rel=1e-9)
    assert branch.pattern == "diverging from run_inlet"
    assert branch.combined_port_id == "run_inlet"
    assert branch.path_head_losses["branch"] == pytest.approx(0.0, abs=1e-9)


def test_isolated_section_is_removed_and_reported() -> None:
    project = dead_end_project()
    built = build_network(project, fluid_properties(project.fluid))
    net = built.network
    leg = built.branch_legs["T1"]["branch"]
    states = [CLOSED if link.index == leg else NORMAL for link in net.links]
    res = solve_gga(net, states, tolerance=1e-9, max_iterations=100)
    assert res.converged
    isolated = {net.nodes[i].key for i in res.isolated_nodes}
    assert isolated == {"T1:branch", "X1:port_1"}
    p3 = built.connections["P3"].link_index
    assert res.isolated_links == [p3]
    assert res.flows[p3] == 0.0
    assert res.flows[leg] == 0.0
    assert math.isnan(res.heads[net.node_index["X1:port_1"]])
    expected = series_flow(10.0, (60.0, 40.0))
    assert res.flows[built.connections["P1"].link_index] == pytest.approx(expected, rel=1e-9)

    outer = OuterLoopResult(res, states, 1, res.iterations, True, [], res.message)
    state = build_solved_state(built, outer, 101325.0, "test")
    assert "X1:port_1" not in state.node_results
    assert "T1:branch" not in state.node_results
    assert "X1" not in state.boundary_results
    assert "T1" not in state.branch_results
    assert state.link_results["P3"].flow == 0.0
    assert state.link_results["P3"].head_loss == 0.0
    [flag] = [f for f in state.flags if f.code == "ISOLATED_SECTION"]
    assert flag.severity == "info"
    assert flag.details["componentIds"] == "T1, X1"


def parallel_project() -> Project:
    """R1 -> P0 -> T1 ==(PA run, PB branch)==> T2 -> P9 -> R2; ideal tees."""
    comps = [reservoir("R1", level=30.0), tee("T1"), tee("T2"), reservoir("R2", level=5.0)]
    conns = [
        connection("P0", ("R1", "port_1"), ("T1", "run_inlet"), length=50.0, diameter=0.15),
        connection("PA", ("T1", "run_outlet"), ("T2", "run_inlet"), length=120.0, diameter=0.1),
        connection("PB", ("T1", "branch"), ("T2", "branch"), length=80.0, diameter=0.08),
        connection("P9", ("T2", "run_outlet"), ("R2", "port_1"), length=50.0, diameter=0.15),
    ]
    return make_project(comps, conns, fluid=custom_fluid(RHO, MU))


def test_parallel_pipes_through_ideal_tees_closed_form() -> None:
    eps = 4.5e-5

    def split(q: float) -> float:  # flow in PA such that h_A = h_B
        return float(
            brentq(
                lambda qa: dw_head(qa, 120.0, 0.1, eps) - dw_head(q - qa, 80.0, 0.08, eps),
                q * 1e-9,
                q * (1 - 1e-9),
                xtol=1e-16,
            )
        )

    def total(q: float) -> float:
        qa = split(q)
        return dw_head(q, 50.0, 0.15, eps) * 2 + dw_head(qa, 120.0, 0.1, eps) - 25.0

    q = brentq(total, 1e-4, 1.0, xtol=1e-15)
    qa = split(q)
    result = solve_project(parallel_project())
    assert result.converged
    links = result.link_results
    assert links["P0"].flow == pytest.approx(q, rel=1e-8)
    assert links["P9"].flow == pytest.approx(q, rel=1e-8)
    assert links["PA"].flow == pytest.approx(qa, rel=1e-8)
    assert links["PB"].flow == pytest.approx(q - qa, rel=1e-8)
    assert result.branch_results["T2"].pattern == "converging to run_outlet"


def looped_project() -> Project:
    """Two reservoirs feeding a two-loop grid of ideal tees with plugged dead ends."""
    comps = [
        reservoir("R1", level=40.0),
        reservoir("R2", elevation=5.0, level=30.0),
        reservoir("R3", level=8.0),
        *(tee(t) for t in ("A", "B", "C", "D", "E", "F")),
        plug("XE"),
    ]
    c = connection
    conns = [
        c("L1", ("R1", "port_1"), ("A", "run_inlet"), length=200, diameter=0.2),
        c("L2", ("A", "run_outlet"), ("B", "run_inlet"), length=300, diameter=0.15),
        c("L3", ("B", "run_outlet"), ("C", "run_inlet"), length=250, diameter=0.15),
        c("L4", ("A", "branch"), ("D", "run_inlet"), length=280, diameter=0.12),
        c("L5", ("D", "run_outlet"), ("E", "run_inlet"), length=300, diameter=0.12),
        c("L6", ("E", "run_outlet"), ("F", "run_inlet"), length=260, diameter=0.1),
        c("L7", ("B", "branch"), ("E", "branch"), length=150, diameter=0.1),
        c("L8", ("C", "branch"), ("F", "branch"), length=170, diameter=0.1),
        c("L9", ("R2", "port_1"), ("C", "run_outlet"), length=400, diameter=0.1),
        c("L10", ("D", "branch"), ("XE", "port_1"), length=50, diameter=0.05),
        c("L11", ("F", "run_outlet"), ("R3", "port_1"), length=500, diameter=0.15),
    ]
    return make_project(comps, conns, fluid=custom_fluid(RHO, MU))


def connection_head(project: Project, conn_id: str, q: float) -> float:
    """h(Q) of a single-segment custom connection, written out with fluids Colebrook."""
    pipe = next(c for c in project.connections if c.id == conn_id).piping.pipes[0]
    assert pipe.inner_diameter is not None
    assert pipe.roughness is not None
    return math.copysign(dw_head(abs(q), pipe.length, pipe.inner_diameter, pipe.roughness), q)


def test_looped_network_satisfies_energy_and_mass_balance_independently() -> None:
    project = looped_project()
    result = solve_project(project)
    assert result.converged
    nodes, links = result.node_results, result.link_results
    for conn in project.connections:
        q = links[conn.id].flow
        if q == 0.0:
            continue
        assert links[conn.id].flow_regime == "turbulent"  # dw_head is the turbulent law
        dh = (
            nodes[node_key(conn.from_component_id, conn.from_port_id)].egl
            - nodes[node_key(conn.to_component_id, conn.to_port_id)].egl
        )
        assert connection_head(project, conn.id, q) == pytest.approx(dh, abs=1e-7), conn.id
    net: dict[str, float] = {}
    for conn in project.connections:
        net[conn.to_component_id] = net.get(conn.to_component_id, 0.0) + links[conn.id].flow
        net[conn.from_component_id] = net.get(conn.from_component_id, 0.0) - links[conn.id].flow
    q_max = max(abs(link.flow) for link in links.values())
    for comp_id, balance in net.items():
        if not comp_id.startswith("R"):
            assert abs(balance) <= 1e-9 * q_max, comp_id
    supply = sum(b.outflow for b in result.boundary_results.values())
    assert supply == pytest.approx(0.0, abs=1e-9 * q_max)
    assert links["L10"].flow == 0.0
    # All three ports of an ideal tee share one EGL.
    for t in ("A", "B", "C", "D", "E", "F"):
        heads = [nodes[f"{t}:{p}"].egl for p in ("run_inlet", "run_outlet", "branch")]
        assert max(heads) - min(heads) <= 1e-9
    assert result.convergence.max_continuity_residual.value <= 1e-9 * q_max
    assert result.convergence.max_energy_residual.value <= 1e-7


def test_jacobian_floor_is_relative_to_the_pipes_in_series() -> None:
    """Nodes 0-1 pipe (slope 2), zero-slope links 2->1 and 2->3, 3-4 pipe (slope 8e6), and a
    link 2->5 with its own slope above its floor, its node 5 joined to node 0 by a pipe. (Branch
    legs are eliminated as head offsets; the floor is for M3's other zero-slope links.)"""
    slopes = np.array([2.0, 0.0, 0.0, 8.0e6, 1.0, 3.0])
    is_pipe = np.array([True, False, False, True, False, True])
    start = np.array([0, 2, 2, 3, 2, 5])
    end = np.array([1, 1, 3, 4, 5, 0])
    used = jacobian_slopes(slopes, is_pipe, start, end, 6)
    assert used[[0, 3, 5]].tolist() == [2.0, 8.0e6, 3.0]  # pipes keep their slope
    assert used[1] == JACOBIAN_FLOOR_RELATIVE * 2.0  # the floor follows its own series pipe,
    assert used[2] == JACOBIAN_FLOOR_RELATIVE * 8.0e6  # not a network-wide statistic
    assert used[4] == 1.0  # a slope above the floor is kept

    # No pipe at either end (not built by the builder): the median pipe slope stands in.
    lone = jacobian_slopes(
        np.array([0.0, 2.0, 4.0, 10.0]),
        np.array([False, True, True, True]),
        np.array([0, 2, 3, 4]),
        np.array([1, 3, 4, 5]),
        6,
    )
    assert lone[0] == JACOBIAN_FLOOR_RELATIVE * 4.0
    zero = jacobian_slopes(
        np.zeros(2), np.zeros(2, dtype=bool), np.array([0, 1]), np.array([1, 2]), 3
    )
    assert np.all(zero == JACOBIAN_FLOOR_ABSOLUTE)


@pytest.mark.parametrize(
    ("d_tube", "l_tube"),
    [
        (0.002, 100.0),  # tubing flow about 1e-8 of the main's
        (0.001, 300.0),  # about 2e-10 of the main's: still a solved flow, not round-off
    ],
)
def test_main_with_small_bore_branch_closed_form(d_tube: float, l_tube: float) -> None:
    """A large main R1 -> T1 -> R2 whose tee branch feeds small-bore tubing to R3 through
    twenty more tees with plugged tubing stubs. Pipe slopes span about nine orders of
    magnitude and most pipes are tubing: a Jacobian floor tied to a network-wide statistic
    (the median slope) exceeded the main's own slope here and stalled Newton.

    Closed form: the stubs carry no flow, the tubing is laminar (Hagen–Poiseuille,
    Q = ΔH g π D⁴ / (128 ν L)), the main is turbulent (fluids Colebrook); the tee EGL H
    solves Q_main(h1 − H) = Q_main(H − h2) + Q_tubing(H) (brentq).
    """
    d_main, l_main, eps = 0.5, 50.0, 4.5e-5
    n_tees = 20
    h1, h2, h3 = 10.0, 8.0, 5.0
    comps = [reservoir("R1", level=h1), reservoir("R2", level=h2), tee("T1")]
    conns = [
        connection("M1", ("R1", "port_1"), ("T1", "run_inlet"), length=l_main, diameter=d_main),
        connection("M2", ("T1", "run_outlet"), ("R2", "port_1"), length=l_main, diameter=d_main),
    ]
    previous = ("T1", "branch")
    for i in range(n_tees):
        comps += [tee(f"S{i}"), plug(f"X{i}")]
        conns += [
            connection(f"A{i}", previous, (f"S{i}", "run_inlet"), length=l_tube, diameter=d_tube),
            connection(
                f"B{i}", (f"S{i}", "branch"), (f"X{i}", "port_1"), length=l_tube, diameter=d_tube
            ),
        ]
        previous = (f"S{i}", "run_outlet")
    comps.append(reservoir("R3", level=h3))
    conns.append(connection("END", previous, ("R3", "port_1"), length=l_tube, diameter=d_tube))

    def q_main(dh: float) -> float:
        if dh == 0.0:
            return 0.0
        return float(brentq(lambda q: dw_head(q, l_main, d_main, eps) - dh, 1e-9, 10.0, xtol=1e-15))

    def q_tubing(h: float) -> float:
        return (h - h3) * g * math.pi * d_tube**4 / (128 * NU * l_tube * (n_tees + 1))

    h_tee = brentq(lambda h: q_main(h1 - h) - q_main(h - h2) - q_tubing(h), h2, h1, xtol=1e-14)
    q_tube = q_tubing(h_tee)
    q1 = q_main(h1 - h_tee)
    assert 4 * q_tube / (math.pi * d_tube * NU) < 2000  # laminar, as the closed form assumes
    assert 4 * q1 / (math.pi * d_main * NU) > 4000  # turbulent: dw_head's Colebrook law

    result = solve_project(make_project(comps, conns, fluid=custom_fluid(RHO, MU)))
    assert result.converged, result.convergence.message
    links = result.link_results
    assert links["M1"].flow == pytest.approx(q1, rel=1e-9)
    assert links["M2"].flow == pytest.approx(q_main(h_tee - h2), rel=1e-9)
    for cid in ["END", *(f"A{i}" for i in range(n_tees))]:
        assert links[cid].flow == pytest.approx(q_tube, rel=1e-6), cid
        assert links[cid].flow_regime == "laminar"
    for i in range(n_tees):
        assert links[f"B{i}"].flow == 0.0
    assert result.node_results["T1:branch"].egl == pytest.approx(h_tee, abs=1e-9)
    # Reported flows close the mass balance at T1 (the tubing flow is not zeroed).
    assert result.convergence.max_continuity_residual.value <= 1e-12 * q1


def test_offset_links_merge_into_trees_with_head_shifts() -> None:
    """Star 0 -> {1, 2} with offsets 0.5 and -0.25, chain 4 -> 3 from a fixed node 4."""
    start = np.array([0, 0, 4, 1])
    end = np.array([1, 2, 3, 5])
    fixed = np.array([False, False, False, False, True, False])
    groups = merge_offset_links(
        6, np.array([0, 1, 2]), np.array([0.5, -0.25, 2.0]), start, end, fixed
    )
    assert groups.root.tolist() == [0, 0, 0, 4, 4, 5]
    # H_node = H_root - shift; H_start - H_end = offset on each link.
    assert groups.shift.tolist() == [0.0, 0.5, -0.25, 2.0, 0.0, 0.0]
    assert groups.parent_link.tolist() == [-1, 0, 1, 2, -1, -1]
    assert sorted(groups.order.tolist()) == [1, 2, 3]

    loop = (np.array([0, 1, 2]), np.array([1, 2, 0]))
    with pytest.raises(ValueError, match="loop"):
        merge_offset_links(3, np.arange(3), np.zeros(3), *loop, np.zeros(3, dtype=bool))
    with pytest.raises(ValueError, match="two fixed heads"):
        merge_offset_links(
            2, np.array([0]), np.zeros(1), np.array([0]), np.array([1]), np.ones(2, dtype=bool)
        )


def test_nonzero_branch_offset_is_imposed_exactly() -> None:
    """R1 -> P1 -> T1 (run) -> P2 -> R2 with a 0.7 m head offset on the run_outlet leg (as
    M3's Crane offsets will set it) and the branch plugged. The path through the tee drops
    H(run_inlet) - H(run_outlet) = offset(run_outlet) - offset(run_inlet) = 0.7 m, so
    H1 - H2 = h_P1(Q) + 0.7 + h_P2(Q) (fluids Colebrook, brentq)."""
    comps = [reservoir("R1", level=20.0), tee("T1"), reservoir("R2", level=10.0), plug("X1")]
    conns = [
        connection("P1", ("R1", "port_1"), ("T1", "run_inlet"), length=60.0),
        connection("P2", ("T1", "run_outlet"), ("R2", "port_1"), length=40.0),
        connection("P3", ("T1", "branch"), ("X1", "port_1"), length=5.0, diameter=0.05),
    ]
    project = make_project(comps, conns, fluid=custom_fluid(RHO, MU))
    built = build_network(project, fluid_properties(project.fluid))
    net = built.network
    leg = net.links[built.branch_legs["T1"]["run_outlet"]]
    assert isinstance(leg.law, HeadOffsetLaw)
    leg.law.offset = 0.7
    res = solve_gga(net, [NORMAL] * len(net.links), tolerance=1e-9, max_iterations=100)
    assert res.converged
    expected = brentq(
        lambda q: dw_head(q, 60.0, 0.1, 4.5e-5) + 0.7 + dw_head(q, 40.0, 0.1, 4.5e-5) - 10.0,
        1e-6,
        1.0,
        xtol=1e-15,
    )
    q = res.flows[built.connections["P1"].link_index]
    assert q == pytest.approx(expected, rel=1e-9)
    assert res.flows[built.connections["P2"].link_index] == pytest.approx(expected, rel=1e-9)
    assert res.flows[built.connections["P3"].link_index] == 0.0
    head = {key: res.heads[i] for key, i in net.node_index.items()}
    center = head[node_key("T1", CENTER_PORT)]
    assert head["T1:run_inlet"] == pytest.approx(center, abs=1e-12)
    assert head["T1:branch"] == pytest.approx(center, abs=1e-12)
    assert center - head["T1:run_outlet"] == pytest.approx(0.7, abs=1e-12)
    assert head["T1:run_inlet"] == pytest.approx(20.0 - dw_head(expected, 60.0, 0.1, 4.5e-5))
    # Leg flows follow from continuity inside the tee: in at run_inlet, out at run_outlet.
    legs = built.branch_legs["T1"]
    assert res.flows[legs["run_outlet"]] == pytest.approx(expected, rel=1e-12)
    assert res.flows[legs["run_inlet"]] == pytest.approx(-expected, rel=1e-12)
    assert res.flows[legs["branch"]] == 0.0
    assert res.max_energy <= 1e-12


def test_iteration_limit_reports_non_convergence() -> None:
    project = looped_project()
    built = build_network(project, fluid_properties(project.fluid))
    states = [NORMAL] * len(built.network.links)
    res = solve_gga(built.network, states, tolerance=1e-9, max_iterations=1)
    assert not res.converged
    assert res.iterations == 1
    assert "not converged after 1 iterations" in res.message
    assert res.max_energy > 0
    assert res.max_energy_link is not None

    outer = OuterLoopResult(res, states, 1, 1, False, [], res.message)
    state = build_solved_state(built, outer, 101325.0, "test")
    assert not state.converged
    assert state.node_results == state.link_results == state.boundary_results == {}
    assert any(f.code == "NOT_CONVERGED" and f.severity == "invalid" for f in state.flags)
    assert state.convergence.max_energy_residual.element_id is not None
    assert "not converged" in state.convergence.message


def test_outer_loop_runs_once_in_m2() -> None:
    project = parallel_project()
    built = build_network(project, fluid_properties(project.fluid))
    outer = run_outer_loop(built, tolerance=1e-9, max_iterations=100)
    assert outer.converged
    assert outer.outer_iterations == 1
    assert outer.inner_iterations == outer.gga.iterations
    legs = [link for link in built.network.links if link.kind is LinkKind.BRANCH_LEG]
    assert len(legs) == 6


def test_wrong_number_of_link_states_is_rejected() -> None:
    project = parallel_project()
    built = build_network(project, fluid_properties(project.fluid))
    with pytest.raises(ValueError, match="one LinkState per link"):
        solve_gga(built.network, [], tolerance=1e-9, max_iterations=10)


def big_bore_stub_chain(with_gate_valves: bool) -> tuple[Project, list[str]]:
    """Review case (seeded, reproduced exactly): a chain of 200 ideal tees on mains of 0.05 to
    3 m, each with a short plugged stub of 0.5 to 5 m bore. The initial flows (1 ft/s) in the
    5 m stubs are about 6 m³/s, while the solved flow is below 1e-3 m³/s."""
    rng = random.Random(3)
    for trial in range(2):  # the review script's second trial
        n = rng.choice([10, 50, 200])
        level_a = rng.uniform(50, 500)
        z_a = rng.uniform(0, 3000)
        comps = [reservoir("RA", level=level_a, elevation=z_a)]
        comps.append(reservoir("RB", level=1.0, elevation=z_a - rng.uniform(1, 100)))
        conns, stubs = [], []
        prev = ("RA", "port_1")
        for i in range(n):
            comps.append(tee(f"T{i}", elevation=z_a + rng.uniform(-50, 50)))
            d_main = rng.choice([0.05, 0.3, 1.0, 3.0])
            conns.append(
                connection(
                    f"C{i}",
                    prev,
                    (f"T{i}", "run_inlet"),
                    length=rng.uniform(1, 2000),
                    diameter=d_main,
                )
            )
            comps.append(plug(f"PL{i}", elevation=z_a + rng.uniform(-50, 50)))
            conns.append(
                connection(
                    f"B{i}",
                    (f"T{i}", "branch"),
                    (f"PL{i}", "port_1"),
                    length=rng.uniform(0.1, 5),
                    diameter=rng.choice([0.5, 2.0, 5.0]),
                    fittings=[{"type": "gate_valve"}] if with_gate_valves else None,
                )
            )
            stubs.append(f"B{i}")
            prev = (f"T{i}", "run_outlet")
        conns.append(connection("CN", prev, ("RB", "port_1"), length=100, diameter=1.0))
        if trial == 1:
            return make_project(comps, conns), stubs
    raise AssertionError("unreachable")


def test_convergence_is_measured_against_the_solved_flows() -> None:
    """Continuity must close to CONTINUITY_RTOL × the solved flows, not × the initial guess."""
    project, _ = big_bore_stub_chain(with_gate_valves=False)
    built = build_network(project, fluid_properties(project.fluid))
    initial = max(link.initial_flow for link in built.network.links)
    res = solve_gga(
        built.network, [NORMAL] * len(built.network.links), tolerance=1e-9, max_iterations=100
    )
    assert res.converged
    q_max = float(np.max(np.abs(res.flows)))
    assert initial > 1e3 * q_max  # premise: the initial guess is a poor flow scale here
    assert res.max_continuity <= CONTINUITY_RTOL * q_max + CONTINUITY_ATOL


def test_plugged_stubs_report_zero_flow_and_no_laminar_flags() -> None:
    project, stubs = big_bore_stub_chain(with_gate_valves=True)
    result = solve_project(project)
    assert result.converged
    assert all(result.link_results[s].flow == 0.0 for s in stubs)
    assert all(result.link_results[s].flow_regime == "none" for s in stubs)
    assert not any(
        f.code == "CORRELATION_OUT_OF_RANGE" and f.connection_id in stubs for f in result.flags
    )


def test_a_network_at_heads_beyond_2_to_the_30_m_converges() -> None:
    """Method 1.2.0's energy stop test (proposal vfd-slice2-discharge-pressure.md §2.11.10,
    fix (b)). Reference nodes at 1e8 and 1e8 − 100 Pa gauge in a liquid of 0.0073 kg/m³ put
    the EGLs near 1.4e9 m, where one unit in the last place is 2⁻²² m (2.4e-7 m), more than
    1e-7 m: method 1.1.0 stalled at that floor for its 100 Newton iterations (energy residual
    1.25e-7 m) and reported the solve as not converged. With the round-off allowance it
    converges, to Hagen–Poiseuille's Q = π D⁴ Δp / (128 μ L) through the two 100 m pipes and
    the ideal tee (Re ≈ 0.1); the plugged branch carries nothing."""
    rho, mu, dp, d = 0.0073, 1.0e-3, 100.0, 0.1  # test inputs
    comps = [
        reference_node("A", pressure=1.0e8),
        tee("T1"),
        plug("X1"),
        reference_node("B", pressure=1.0e8 - dp),
    ]
    conns = [
        connection("P1", ("A", "port_1"), ("T1", "run_inlet"), length=100.0, diameter=d),
        connection("P2", ("T1", "run_outlet"), ("B", "port_1"), length=100.0, diameter=d),
        connection("S1", ("T1", "branch"), ("X1", "port_1"), length=1.0, diameter=d),
    ]
    result = solve_project(make_project(comps, conns, fluid=custom_fluid(rho, mu)))
    assert result.converged
    assert result.node_results["T1:run_inlet"].egl > 2.0**30  # premise: the floor is there
    expected = math.pi * d**4 * dp / (128 * mu * 200.0)
    assert result.link_results["P1"].flow == pytest.approx(expected, rel=1e-9)
    assert result.link_results["P2"].flow == pytest.approx(expected, rel=1e-9)
    assert result.link_results["P1"].flow_regime == "laminar"
    assert result.link_results["S1"].flow == 0.0
    assert result.convergence.inner_iterations < 20
