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


def test_without_a_lost_weight_the_plain_message_stays() -> None:
    """Guard of new code: a step with nothing lost (every weight 1) finds no cause, and the
    message is SINGULAR alone, so nothing is named falsely."""
    from opensolve_pipe.services.solver.gga import SINGULAR as GGA_SINGULAR
    from opensolve_pipe.services.solver.gga import lost_weights, singular_message

    sc = np.array([-1, 0], dtype=np.int64)
    ec = np.array([0, 1], dtype=np.int64)
    assert lost_weights(np.ones(2), sc, ec, 2) == []
    assert singular_message([], 0) == GGA_SINGULAR == SINGULAR
