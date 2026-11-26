"""A Newton step whose matrix is singular in floating point, named (TSD §12 item 19; proposal
open-defects-2.md §3 A2b, method 1.6.2).

GGA's Schur matrix A21 D⁻¹ A12 adds the weights 1/(dh/dQ) of the links at a free node into one
diagonal entry. A weight that the sum of the others absorbs in rounding (fl(S + w) = S, IEEE 754
round to nearest) is lost from it. When every link that joins a part of the free nodes to the
fixed heads is lost so at its end in that part, the part's rows are an ungrounded Laplacian in
floating point and SuperLU finds the matrix singular, though the steady state is determined. The
step is unchanged (the case still does not converge; proposal §7); the message and the
NOT_CONVERGED flag now name each such link, its slope, its flow and its loss coefficient, and say
which iterate they quote (``singularStepAt``, ``singularStepFlow``, ``singularStepSlope``,
``singularStepCoefficient``). Where no lost weight is found the plain message stays.

The first step's threshold is a closed form. R1 (10 m) -> 10 m of 0.1 m pipe -> gate valve V1 ->
10 m of pipe -> AF1, in 998 kg/m³ and 1 mPa·s: at the start flow Q0 = 1 ft/s × πD²/4 (EPANET
2.2's initlinkflow, TSD §5.2), V1:outlet's diagonal is w_v + w2, with w_v = 1/(2 c Q0) (the
valve's law, h = c Q|Q|, D9) and w2 the downstream pipe's weight. w2 is computed here from fluids'
Colebrook factor (``fluids.friction.Clamond``, D1, D8) and its local exponent: it lies in
[2⁻⁴, 2⁻³), so ulp(w2) = 2⁻⁵⁶ and w_v is lost exactly when w_v < ulp(w2)/2, that is when
c > c* = 2⁵⁶/Q0. Expected values come from that closed form, never from the solver.
"""

import math
import re
from typing import Any

import fluids.fittings
import fluids.friction
import numpy as np
import pytest
from fluids.constants import foot, g

from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import Flag, SolvedState
from opensolve_pipe.services.fluids import fluid_properties
from opensolve_pipe.services.solver import solve_project
from opensolve_pipe.services.solver.builder import build_network
from opensolve_pipe.services.solver.gga import solve_gga
from opensolve_pipe.services.solver.network import NORMAL
from opensolve_pipe.services.solver.status import initial_controls, link_states

from .helpers import (
    assigned_flow,
    connection,
    custom_fluid,
    custom_pipe,
    plug,
    project_dict,
    reservoir,
    tee,
)

SINGULAR = "the linear system could not be solved (singular matrix)"
D, LENGTH, EPS, RHO, MU = 0.1, 10.0, 4.5e-5, 998.0, 1.0e-3
AREA = math.pi * D**2 / 4.0
Q0 = foot * AREA
"""m³/s: the start flow, 1 ft/s in the 0.1 m pipe."""
C_STAR = 2.0**56 / Q0
"""s²/m⁵: the first step's threshold (module docstring)."""
NUM = r"(-?\d+(?:\.\d+)?(?:e[+-]\d+)?)"
ONE = (
    "is lost in rounding: added to the weights of the other links at its end beyond it, it "
    "leaves their sum unchanged, so the network beyond it, which reaches a fixed or held head "
    "only through it, has none in the Newton step"
)
"""The words after one named link: true of every head the Newton step holds fixed (a
reservoir's or reference node's, an active PRV's or PSV's held head, a floating section's held
level; review of open defects round two, AS-2)."""
MANY = (
    "are lost in rounding: added to the weights of the other links at their ends beyond them, "
    "each leaves that sum unchanged, so the network beyond them, which reaches a fixed or held "
    "head only through them, has none in the Newton step"
)


def pipe_weight(q: float, length: float = LENGTH, d: float = D) -> float:
    """1/(dh/dQ) of a Darcy-Weisbach pipe at flow q: h = f L/D v²/(2g), and dh/dQ = (h/Q)(2 +
    d ln f/d ln Re), the exponent from fluids' Colebrook factor by a central difference."""
    area = math.pi * d**2 / 4.0
    v = q / area
    re_d, ed = RHO * v * d / MU, EPS / d
    f = float(fluids.friction.Clamond(re_d, ed))
    step = 1.0e-6
    up = math.log(float(fluids.friction.Clamond(re_d * (1 + step), ed)))
    down = math.log(float(fluids.friction.Clamond(re_d * (1 - step), ed)))
    exponent = (up - down) / (math.log1p(step) - math.log1p(-step))
    loss = f * length / d * v * v / (2.0 * g)
    return 1.0 / (loss / q * (2.0 + exponent))


def cv_of(c: float) -> float:
    """The Cv whose valve coefficient on the 0.1 m pipe is c: K = c·2gA², Cv by fluids (D9)."""
    return float(fluids.fittings.K_to_Cv(c * 2.0 * g * AREA * AREA, D))


def c_of(cv: float) -> float:
    return float(fluids.fittings.Cv_to_K(cv, D)) / (2.0 * g * AREA * AREA)


def valve(cid: str, cv: float) -> dict[str, Any]:
    return {
        "type": "valve",
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "valveType": "gate",
        "resistance": {"kind": "Cv", "value": cv},
        "ports": [{"id": "inlet", "nominalSize": 0.1}, {"id": "outlet", "nominalSize": 0.1}],
    }


def pipes(length: float = LENGTH, d: float = D) -> list[dict[str, Any]]:
    return [custom_pipe(length, d, EPS)]


def bridge(cv: float, end: str = "af") -> Project:
    """R1 -> L1 -> V1 -> L2 -> AF1 (0.01 m³/s out) or a plug."""
    far = assigned_flow("AF1", 0.01) if end == "af" else plug("AF1")
    data = project_dict(
        [reservoir("R1", level=10.0), valve("V1", cv), far],
        [
            connection("L1", ("R1", "port_1"), ("V1", "inlet"), pipes=pipes()),
            connection("L2", ("V1", "outlet"), ("AF1", "port_1"), pipes=pipes()),
        ],
        fluid=custom_fluid(RHO, MU),
    )
    return Project.model_validate(data)


def series(cv1: float, cv2: float) -> Project:
    """R1 (10 m) -> L1 -> V1 -> L2 -> V2 -> L3 -> AF1 (0.01 m³/s out)."""
    data = project_dict(
        [
            reservoir("R1", level=10.0),
            valve("V1", cv1),
            valve("V2", cv2),
            assigned_flow("AF1", 0.01),
        ],
        [
            connection("L1", ("R1", "port_1"), ("V1", "inlet"), pipes=pipes()),
            connection("L2", ("V1", "outlet"), ("V2", "inlet"), pipes=pipes()),
            connection("L3", ("V2", "outlet"), ("AF1", "port_1"), pipes=pipes()),
        ],
        fluid=custom_fluid(RHO, MU),
    )
    return Project.model_validate(data)


def plugged_branch(cv: float) -> Project:
    """R1 (10 m) -> L1 -> V1 -> L2 -> ideal tee T1, whose run feeds AF1 (0.01 m³/s out) through
    L3 and whose branch runs through L4, V2 and L5 to a plug PL (the skeptic's network in the
    review of the AS-3 fix); both valves at ``cv``."""
    data = project_dict(
        [
            reservoir("R1", level=10.0),
            valve("V1", cv),
            tee("T1"),
            assigned_flow("AF1", 0.01),
            valve("V2", cv),
            plug("PL"),
        ],
        [
            connection("L1", ("R1", "port_1"), ("V1", "inlet"), pipes=pipes()),
            connection("L2", ("V1", "outlet"), ("T1", "run_inlet"), pipes=pipes()),
            connection("L3", ("T1", "run_outlet"), ("AF1", "port_1"), pipes=pipes()),
            connection("L4", ("T1", "branch"), ("V2", "inlet"), pipes=pipes()),
            connection("L5", ("V2", "outlet"), ("PL", "port_1"), pipes=pipes()),
        ],
        fluid=custom_fluid(RHO, MU),
    )
    return Project.model_validate(data)


def floating_section(cv: float) -> Project:
    """R1 (20 m) -> P0 -> V1 (isolated) -> P1 -> V9 -> P5 -> ideal tee T1, whose run feeds D1
    (0.01 m³/s out) through P2 and whose branch S1 feeds (0.01 m³/s in) through P3: behind the
    isolated V1 the rest is a floating section, its assigned flows balanced (review of open
    defects round two, AS-2)."""
    isolated = {**valve("V1", 1.0), "status": "isolated"}
    data = project_dict(
        [
            reservoir("R1", level=20.0),
            isolated,
            valve("V9", cv),
            tee("T1"),
            assigned_flow("D1", 0.01),
            assigned_flow("S1", -0.01),
        ],
        [
            connection("P0", ("R1", "port_1"), ("V1", "inlet"), pipes=pipes()),
            connection("P1", ("V1", "outlet"), ("V9", "inlet"), pipes=pipes()),
            connection("P5", ("V9", "outlet"), ("T1", "run_inlet"), pipes=pipes()),
            connection("P2", ("T1", "run_outlet"), ("D1", "port_1"), pipes=pipes()),
            connection("P3", ("T1", "branch"), ("S1", "port_1"), pipes=pipes()),
        ],
        fluid=custom_fluid(RHO, MU),
    )
    return Project.model_validate(data)


def first_step(project: Project) -> tuple[int, str]:
    """One inner solve of one Newton step from the start flows: its iterations and message."""
    built = build_network(project, fluid_properties(project.fluid))
    states = [NORMAL] * len(built.network.links)
    result = solve_gga(built.network, states, tolerance=1.0e-9, max_iterations=1)
    return result.iterations, result.message


def not_converged(state: SolvedState) -> Flag:
    assert not state.converged
    [flag] = [f for f in state.flags if f.code == "NOT_CONVERGED"]
    return flag


def named_terms(message: str) -> list[tuple[str, float, float, float | None]]:
    """Each link the message names: (id, slope, flow, coefficient or None)."""
    pattern = (
        rf"'([\w-]+)' \(a slope of {NUM} s/m² at a flow of {NUM} m³/s"
        rf"(?:; [^=]+ = {NUM} s²/m⁵)?\)"
    )
    return [
        (m[1], float(m[2]), float(m[3]), float(m[4]) if m[4] else None)
        for m in re.finditer(pattern, message)
    ]


# --------------------------------------------------------------------------- the mechanism


def test_the_downstream_weight_lies_in_one_binade_so_the_threshold_is_closed_form() -> None:
    """w2 from fluids lies well inside [2⁻⁴, 2⁻³) (the local exponent's few-percent effect cannot
    move it out), so ulp(w2) = 2⁻⁵⁶; and the valve's weight at c* is exactly half of it."""
    w2 = pipe_weight(Q0)
    assert 2.0**-4 * 1.05 < w2 < 2.0**-3 * 0.95
    assert np.spacing(w2) == 2.0**-56
    w_v = 1.0 / (2.0 * C_STAR * Q0)
    assert w_v == pytest.approx(2.0**-57, rel=1e-15)


@pytest.mark.parametrize("end", ["af", "plug"])
def test_the_first_step_is_singular_exactly_past_the_closed_form_threshold(end: str) -> None:
    """Just past c* (by 1e-9) V1's weight is lost from V1:outlet's diagonal and the first step is
    singular; just below it the step is taken. The message names V1, says that it quotes the
    first Newton iteration at the starting flows, and gives its slope 2cQ0, the flow Q0 and its
    coefficient c (HEAD: the plain message on the singular side)."""
    above, below = cv_of(C_STAR * (1.0 + 1.0e-9)), cv_of(C_STAR * (1.0 - 1.0e-9))
    assert c_of(above) > C_STAR > c_of(below)
    iterations, message = first_step(bridge(below, end))
    assert iterations == 1, message
    assert not message.startswith(SINGULAR), message
    iterations, message = first_step(bridge(above, end))
    assert iterations == 0
    assert message.startswith(
        f"{SINGULAR}: in Newton iteration 1, at the starting flows, the weight 1/(dh/dQ) of 'V1' "
    ), message
    c = c_of(above)
    [(cid, slope, flow, coefficient)] = named_terms(message)
    assert cid == "V1"
    assert slope == pytest.approx(2.0 * c * Q0, rel=5e-3)
    assert flow == pytest.approx(Q0, rel=5e-3)
    assert coefficient == pytest.approx(c, rel=1e-5)


def test_a_solve_started_from_a_previous_solves_flows_says_so() -> None:
    """An inner solve given its starting flows (a later outer iteration after a status change, a
    warm-started system curve point or goal-seek trial) quotes them as the previous solve's, not
    as the starting flows: the same singular first step, from the same flows handed in."""
    project = bridge(cv_of(C_STAR * (1.0 + 1.0e-9)), "af")
    built = build_network(project, fluid_properties(project.fluid))
    states = [NORMAL] * len(built.network.links)
    flows = np.array([link.initial_flow for link in built.network.links], dtype=np.float64)
    result = solve_gga(
        built.network, states, tolerance=1.0e-9, max_iterations=1, initial_flows=flows
    )
    assert result.iterations == 0
    assert result.message.startswith(
        f"{SINGULAR}: in Newton iteration 1, at the previous solve's flows, the weight 1/(dh/dQ) "
        "of 'V1' "
    ), result.message


def test_the_message_says_which_iterate_of_which_solve() -> None:
    """Which iterate the step was taken from: the starting flows or the previous solve's (step
    1), else the flows after the steps before it, of a solve started from the previous solve's
    flows where it was (guard of the words, every branch)."""
    from opensolve_pipe.services.solver.gga import LostWeight, singular_message

    item = LostWeight(
        link=0, element_id="V1", flow=1.0e-3, slope=2.0, coefficient=None, coefficient_name=""
    )
    words = {
        (0, False): "in Newton iteration 1, at the starting flows, ",
        (0, True): "in Newton iteration 1, at the previous solve's flows, ",
        (2, False): "in Newton iteration 3, at the flows after iteration 2, ",
        (2, True): (
            "in Newton iteration 3 of a solve started from the previous solve's flows, at the "
            "flows after iteration 2, "
        ),
    }
    for (iteration, resumed), expected in words.items():
        message = singular_message([item], iteration, resumed=resumed)
        assert message.startswith(f"{SINGULAR}: {expected}the weight 1/(dh/dQ) of 'V1' "), message


def test_the_flag_names_the_lost_weight_with_its_values() -> None:
    """The whole solve at Cv 1e-6 (c ≈ 1.77e20, far past c*): the NOT_CONVERGED details carry V1,
    its flow, slope and coefficient as numbers (HEAD: none of them)."""
    project = bridge(1.0e-6)
    state = solve_project(project)
    flag = not_converged(state)
    c = c_of(1.0e-6)
    assert c > C_STAR
    assert state.convergence.message.startswith(
        f"{SINGULAR}: in Newton iteration 1, at the starting flows, the weight 1/(dh/dQ) of 'V1' "
    )
    assert flag.details["singularStepAt"] == "V1"
    assert flag.details["singularStepFlow"] == pytest.approx(Q0, rel=1e-12)
    assert flag.details["singularStepSlope"] == pytest.approx(2.0 * c * Q0, rel=1e-12)
    assert flag.details["singularStepCoefficient"] == pytest.approx(c, rel=1e-12)
    assert flag.message == f"the solve did not converge: {state.convergence.message}"


def test_a_weight_lost_beside_a_floating_sections_held_level_is_named_in_true_words() -> None:
    """Behind the isolated V1 no reservoir or reference node reaches the rest: the solve holds
    the first node of that floating section, V1:outlet, at an arbitrary level
    (``gga.FLOATING_REFERENCE_HEAD``), a head its Newton step holds fixed. V9 (Cv 1e-6) alone
    joins the rest of the section to it, and its weight is lost at V9:outlet in Newton iteration
    6 (measured; the review's network). The message names V9 in words true of that held level
    (HEAD: "which reaches a reservoir or reference node only through it", where none is
    reached), and the plain bridge beyond R1 names V1 in the same words."""
    project = floating_section(1.0e-6)
    built = build_network(project, fluid_properties(project.fluid))
    states = link_states(built, initial_controls(built))
    inner = solve_gga(built.network, states, tolerance=1.0e-9, max_iterations=100)
    [section] = inner.floating_sections
    assert section[0] == built.network.node_index["V1:outlet"]
    assert [item.element_id for item in inner.lost_weights] == ["V9"]
    state = solve_project(project)
    flag = not_converged(state)
    message = state.convergence.message
    assert flag.details["singularStepAt"] == "V9"
    assert [t[0] for t in named_terms(message)] == ["V9"]
    assert message.startswith(
        f"{SINGULAR}: in Newton iteration 6, at the flows after iteration 5, the weight "
        "1/(dh/dQ) of 'V9' "
    ), message
    assert message.endswith(ONE), message
    assert "reaches a reservoir or reference node" not in message
    plain = solve_project(bridge(1.0e-6))
    assert not_converged(plain).details["singularStepAt"] == "V1"
    assert [t[0] for t in named_terms(plain.convergence.message)] == ["V1"]
    assert plain.convergence.message.endswith(ONE), plain.convergence.message


# --------------------------------------------------------------------------- not the cause


def test_a_lost_weight_whose_ends_stay_grounded_is_not_named() -> None:
    """VH, between the reservoirs in series with pipes, is lost too, but each of its ends stays
    grounded through a pipe of its own: only the bridge V1 cuts a part off. The largest energy
    error still lies on VH (the residual is truly largest there; CLAUDE.md D7: the largest
    residual can lie elsewhere), so the flag's two names differ (HEAD: VH alone)."""
    data = project_dict(
        [
            reservoir("R1", level=10.0, ports=("port_1", "port_2", "port_3")),
            reservoir("R2", level=0.0, ports=("port_1", "port_2")),
            valve("VH", 1.0e-8),
            valve("V1", 1.0e-7),
            assigned_flow("AF1", 0.01),
        ],
        [
            connection("L1", ("R1", "port_1"), ("R2", "port_1"), pipes=pipes()),
            connection("L2", ("R1", "port_2"), ("VH", "inlet"), pipes=pipes()),
            connection("L3", ("VH", "outlet"), ("R2", "port_2"), pipes=pipes()),
            connection("L4", ("R1", "port_3"), ("V1", "inlet"), pipes=pipes()),
            connection("L5", ("V1", "outlet"), ("AF1", "port_1"), pipes=pipes()),
        ],
        fluid=custom_fluid(RHO, MU),
    )
    state = solve_project(Project.model_validate(data))
    flag = not_converged(state)
    assert flag.details["singularStepAt"] == "V1"
    assert [t[0] for t in named_terms(state.convergence.message)] == ["V1"]
    assert "'VH'" not in state.convergence.message
    assert flag.details["maxEnergyResidualAt"] == "VH"


def test_two_lost_weights_that_together_cut_a_part_off_are_named_in_link_order() -> None:
    """VA and VB in parallel from R1 into an ideal tee that feeds AF1: neither alone cuts the
    tee off, both together do. Both are named, in link order, in the plural form."""
    data = project_dict(
        [
            reservoir("R1", level=10.0, ports=("port_1", "port_2")),
            valve("VA", 1.0e-7),
            valve("VB", 1.0e-7),
            tee("T1"),
            assigned_flow("AF1", 0.01),
        ],
        [
            connection("L1", ("R1", "port_1"), ("VA", "inlet"), pipes=pipes()),
            connection("L2", ("VA", "outlet"), ("T1", "run_inlet"), pipes=pipes()),
            connection("L3", ("R1", "port_2"), ("VB", "inlet"), pipes=pipes()),
            connection("L4", ("VB", "outlet"), ("T1", "branch"), pipes=pipes()),
            connection("L5", ("T1", "run_outlet"), ("AF1", "port_1"), pipes=pipes()),
        ],
        fluid=custom_fluid(RHO, MU),
    )
    state = solve_project(Project.model_validate(data))
    flag = not_converged(state)
    assert flag.details["singularStepAt"] == "VA, VB"
    message = state.convergence.message
    assert [t[0] for t in named_terms(message)] == ["VA", "VB"]
    assert "the weights 1/(dh/dQ) of 'VA'" in message
    assert " are lost in rounding" in message
    assert message.endswith(MANY), message


def test_two_lost_valves_in_series_are_both_named() -> None:
    """V1 and V2 (Cv 1e-6 each) in series between R1 and AF1, in water: in the singular step
    each one's weight is lost at both its ends (the review measured iteration 7). The part
    between them, {V1:outlet, V2:inlet}, reaches R1 only through V1, and the part beyond V2,
    {V2:outlet, AF1}, only through V2 and then V1: both are named, in link order, in the plural
    (HEAD: V1 alone, though the part beyond V2 reaches the fixed head only through V2). With V1
    at Cv 1.0, whose weight is kept, V2 alone is named (as on HEAD)."""
    state = solve_project(series(1.0e-6, 1.0e-6))
    flag = not_converged(state)
    assert flag.details["singularStepAt"] == "V1, V2"
    message = state.convergence.message
    assert [t[0] for t in named_terms(message)] == ["V1", "V2"]
    assert "the weights 1/(dh/dQ) of 'V1'" in message
    assert message.endswith(MANY), message
    state = solve_project(series(1.0, 1.0e-6))
    flag = not_converged(state)
    assert flag.details["singularStepAt"] == "V2"
    assert [t[0] for t in named_terms(state.convergence.message)] == ["V2"]
    assert state.convergence.message.endswith(ONE), state.convergence.message


def test_a_valve_before_a_plug_lost_at_both_its_ends_is_named_from_the_plugged_end() -> None:
    """V1 (Cv 1e-6) from R1 into a tee that feeds AF1, and V2 (Cv 1e-6) on the tee's branch
    before a plug (``plugged_branch``). At the starting flows each valve meets one pipe at each
    end, every link at Q0, and its weight 1/(2 c Q0) is lost beside the pipe's (c > c*, module
    docstring). The tee's part {V1:outlet, T1, AF1, V2:inlet} reaches R1 only through V1; the
    plugged part {V2:outlet, PL}, a dead end beyond the tee's part, only through V2 and then V1.
    V2 leads from the tee's part only to that dead end, but from its plugged end it is the
    dead end's one way to R1: both are named, in link order, with the slope 2cQ0, the flow Q0
    and the coefficient c (HEAD: V1 alone)."""
    c = c_of(1.0e-6)
    assert c > C_STAR
    w_valve, w_pipe = 1.0 / (2.0 * c * Q0), pipe_weight(Q0)
    assert w_pipe + w_valve == w_pipe
    state = solve_project(plugged_branch(1.0e-6))
    flag = not_converged(state)
    assert flag.details["singularStepAt"] == "V1, V2"
    message = state.convergence.message
    assert message.startswith(
        f"{SINGULAR}: in Newton iteration 1, at the starting flows, the weights 1/(dh/dQ) of 'V1' "
    ), message
    terms = named_terms(message)
    assert [t[0] for t in terms] == ["V1", "V2"]
    for _, slope, flow, coefficient in terms:
        assert slope == pytest.approx(2.0 * c * Q0, rel=5e-3)
        assert flow == pytest.approx(Q0, rel=5e-3)
        assert coefficient == pytest.approx(c, rel=1e-5)
    assert message.endswith(MANY), message


def test_a_steep_pipe_is_named_with_its_laminar_slope_and_no_coefficient() -> None:
    """1e6 m of 1 mm pipe from R1 into an ideal tee whose other legs are 1 mm of 1 m pipe, to
    AF1 (1e-6 m³/s) and a plug: the steep pipe's weight is lost beside the wide ones. Laminar at
    its flows (Re ≈ 1.3e3 at 1e-6 m³/s), its slope is Hagen-Poiseuille's, 128 μ L/(π ρ g D⁴),
    whatever the flow; a pipe's friction has no single coefficient, so none is quoted."""
    data = project_dict(
        [reservoir("R1", level=10.0), tee("T1"), assigned_flow("AF1", 1.0e-6), plug("PL")],
        [
            connection("L1", ("R1", "port_1"), ("T1", "run_inlet"), pipes=pipes(1.0e6, 1.0e-3)),
            connection("L2", ("T1", "run_outlet"), ("AF1", "port_1"), pipes=pipes(1.0e-3, 1.0)),
            connection("L3", ("T1", "branch"), ("PL", "port_1"), pipes=pipes(1.0e-3, 1.0)),
        ],
        fluid=custom_fluid(RHO, MU),
    )
    state = solve_project(Project.model_validate(data))
    flag = not_converged(state)
    assert flag.details["singularStepAt"] == "L1"
    laminar = 128.0 * MU * 1.0e6 / (math.pi * RHO * g * 1.0e-3**4)
    assert flag.details["singularStepSlope"] == pytest.approx(laminar, rel=1e-9)
    assert "singularStepCoefficient" not in flag.details
    [(cid, slope, _, coefficient)] = named_terms(state.convergence.message)
    assert (cid, coefficient) == ("L1", None)
    assert slope == pytest.approx(laminar, rel=5e-3)


# --------------------------------------------------------------------------- lost_weights itself


def test_a_weight_is_lost_only_where_the_others_sum_absorbs_it_across_a_binade() -> None:
    """Guard of new code (``gga.lost_weights``). A bridge (position 1) from a grounded node
    (column 0) to a dead end (columns 1, 2), whose far diagonal is w + S with S = nextafter(2, 0):
    at w = ulp(S)/4 the sum is S (lost: the far part has no fixed head and the bridge is named);
    at w = ulp(S)/2 and 3ulp(S)/4 it rounds up to 2.0, across the binade, so w is kept, although
    w ≤ spacing(2.0)/2, the half-ulp test on the assembled entry, would call it lost."""
    from opensolve_pipe.services.solver.gga import lost_weights

    s_far = math.nextafter(2.0, 0.0)
    ulp = 2.0**-52
    assert np.spacing(s_far) == ulp
    sc = np.array([-1, 0, 1], dtype=np.int64)  # fixed -> 0, 0 -> 1 (the bridge), 1 -> 2
    ec = np.array([0, 1, 2], dtype=np.int64)
    for share, lost in ((0.25, True), (0.5, False), (0.75, False)):
        w = share * ulp
        assert ((s_far + w) == s_far) is lost
        d_inv = np.array([1.0, w, s_far])
        assert lost_weights(d_inv, sc, ec, 3) == ([1] if lost else [])
    assert 0.75 * ulp <= np.spacing(2.0) / 2.0  # the old test's false positive


def test_a_lost_weight_beside_a_grounded_end_is_not_named() -> None:
    """Guard of new code: the bridge's weight lost only at its grounded end (column 0, beside a
    weight of 1) and kept at its far end (beside a weight of the same size) cuts nothing off."""
    from opensolve_pipe.services.solver.gga import lost_weights

    w = 2.0**-60
    sc = np.array([-1, 0, 1], dtype=np.int64)
    ec = np.array([0, 1, 2], dtype=np.int64)
    assert (1.0 + w) == 1.0
    assert (w + w) != w
    assert lost_weights(np.array([1.0, w, w]), sc, ec, 3) == []


def test_two_lost_bridges_in_series_are_both_named_by_lost_weights() -> None:
    """Guard of new code (``gga.lost_weights``, AS-3): the series line's columns and weights as
    the review measured them in its singular step (``series``, Cv 1e-6 each; positions L1, L2,
    L3, V1, V2; d_inv to 4 digits). Each valve's weight is lost at both its ends. Weights kept at
    both ends join columns 1 and 2 (L2), and 3 and 4 (L3); L1 grounds column 0. V1 (position 3)
    joins {1, 2} to the grounded column 0; V2 (position 4) joins {3, 4} to {1, 2}, which reaches
    the fixed head through V1, not back through {3, 4}: both are named (HEAD: [3])."""
    from opensolve_pipe.services.solver.gga import lost_weights

    sc = np.array([-1, 1, 3, 0, 2], dtype=np.int64)
    ec = np.array([0, 2, 4, 1, 3], dtype=np.int64)
    d_inv = np.array([8.438e-03, 8.402e-03, 4.598e-03, 6.645e-20, 6.625e-20])
    for valve_pos, (at_start, at_end) in ((3, (0, 1)), (4, (2, 3))):
        for column in (at_start, at_end):
            others = [d_inv[p] for p in range(5) if p != valve_pos and column in (sc[p], ec[p])]
            assert len(others) == 1
            assert others[0] + d_inv[valve_pos] == others[0]
    assert lost_weights(d_inv, sc, ec, 5) == [3, 4]


def test_a_lost_link_that_leads_only_back_to_its_own_part_is_not_named() -> None:
    """Guard of new code (``gga.lost_weights``, AS-3; passes on HEAD too). Y (position 0) runs
    from the fixed head to column 0, a pipe of weight 1 (position 1) joins columns 0 and 1, X
    (position 2) runs from column 1 to column 2, where it is alone, and a chord C (position 3)
    joins columns 0 and 1 again. Y, X and C weigh 2⁻⁶⁰: lost beside the pipe at columns 0 and
    1 (1 + 2⁻⁶⁰ + 2⁻⁶⁰ rounds to 1), X kept at column 2. {0, 1} reaches the fixed head only
    through Y, which is named. X leads to {2}, which reaches the fixed head only back through
    {0, 1}, so X joins nothing to a fixed head; C joins {0, 1} to itself. Neither is named."""
    from opensolve_pipe.services.solver.gga import lost_weights

    w = 2.0**-60
    sc = np.array([-1, 0, 1, 0], dtype=np.int64)
    ec = np.array([0, 1, 2, 1], dtype=np.int64)
    assert math.fsum([1.0, w]) == 1.0
    assert math.fsum([1.0, w]) + w == 1.0
    assert lost_weights(np.array([w, 1.0, w, w]), sc, ec, 3) == [0]


def test_a_link_lost_at_a_dead_ends_own_end_is_named_from_there() -> None:
    """Guard of new code (``gga.lost_weights``, AS-3: each end is examined on its own). Y
    (position 0) runs from the fixed head to column 0, a pipe (position 1) joins columns 0 and
    1, X (position 2) runs from column 1 to column 2, and a pipe (position 3) joins columns 2
    and 3, a dead end. Y weighs 2⁻⁶⁰ and is lost beside the pipe of weight 1 at column 0, so
    {0, 1} reaches the fixed head only through Y, and {2, 3} only through X and then Y.
    X at 2⁻⁶⁰ with the far pipe at 1 is lost at both its ends (1 + 2⁻⁶⁰ rounds to 1), and is
    named from its end at column 2, as V2 before the plug is (HEAD: [0]). X at 1 with the far
    pipe at 2⁶⁰ is kept at column 1 (1 + 1 = 2) and lost at column 2 alone (ulp(2⁶⁰) = 2⁸):
    named from there too (HEAD: [0]). X at 2⁻⁶⁰ with the far pipe at 2⁻⁶⁰ is kept at column 2
    (2⁻⁶⁰ + 2⁻⁶⁰ = 2⁻⁵⁹): lost only at column 1, it leads from {0, 1} only to the dead end
    beyond it, and is not named."""
    from opensolve_pipe.services.solver.gga import lost_weights

    w, big = 2.0**-60, 2.0**60
    sc = np.array([-1, 0, 1, 2], dtype=np.int64)
    ec = np.array([0, 1, 2, 3], dtype=np.int64)
    assert 1.0 + w == 1.0
    assert w + w != w
    assert big + 1.0 == big
    assert 1.0 + 1.0 != 1.0
    assert lost_weights(np.array([w, 1.0, w, 1.0]), sc, ec, 4) == [0, 2]
    assert lost_weights(np.array([w, 1.0, 1.0, big]), sc, ec, 4) == [0, 2]
    assert lost_weights(np.array([w, 1.0, w, w]), sc, ec, 4) == [0]


def test_without_a_lost_weight_the_plain_message_stays() -> None:
    """Guard of new code: a step with nothing lost (every weight 1) finds no cause, and the
    message is SINGULAR alone, so nothing is named falsely."""
    from opensolve_pipe.services.solver.gga import SINGULAR as GGA_SINGULAR
    from opensolve_pipe.services.solver.gga import lost_weights, singular_message

    sc = np.array([-1, 0], dtype=np.int64)
    ec = np.array([0, 1], dtype=np.int64)
    assert lost_weights(np.ones(2), sc, ec, 2) == []
    assert singular_message([], 0) == GGA_SINGULAR == SINGULAR
