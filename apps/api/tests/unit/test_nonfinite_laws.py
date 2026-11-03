"""Loss laws whose values are not finite numbers (open item 2, verified on 7fcbdb8, 2026-11-03).

(a) Where the GGA stops because a value of its iterate is not a finite number ("the iteration
diverged"), the NOT_CONVERGED flag names the laws that gave one (CLAUDE.md D7: the flag names
where the solve failed): the message quotes each element's id, what was not finite, the flow
and the law's loss coefficient c (h = c Q|Q|), and the flag's details carry ``nonFiniteLawAt``
(every id) and the first one's ``nonFiniteLawFlow`` and ``nonFiniteLawCoefficient``. Before,
the message named nothing, and the largest residual could lie on another element.

(b) A quadratic loss law forms its slope dh/dQ = 2c|Q| as (2c)·|Q|, so a finite c above half
the largest double (``SLOPE_COEFFICIENT_MAX``) gives a slope that is not a finite number at
every flow, and the solve could only fail on it. VALVE_RESISTANCE_OUT_OF_RANGE,
FITTING_RESISTANCE_OUT_OF_RANGE, EQUIPMENT_RATING_OUT_OF_RANGE and ORIFICE_OUT_OF_RANGE refuse
such an element before the solve, in an added message form quoting c and the bound; an element
whose c is at the bound is accepted and solves.

A pipe whose Reynolds-number denominator A ν underflows to 0 raised ZeroDivisionError (500) and
is now PIPE_SIZE_OUT_OF_RANGE (found by the same verification).

Every coefficient here is computed in the test from its definition (D18, D9, D22, D20), with
fluids' g and conversions; the start flow is 1 ft/s in the element's inlet pipe (EPANET 2.2's
initlinkflow, TSD §5.2).
"""

import math
import re
import struct
import sys
from typing import Any

import fluids.fittings
import fluids.friction
import pytest
from fluids.constants import foot, g

from opensolve_pipe.models.components import OrificeTaps
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import Flag, SolvedState
from opensolve_pipe.services.fluids import fluid_properties
from opensolve_pipe.services.solver import solve_project
from opensolve_pipe.services.solver.builder import BuiltNetwork, build_network
from opensolve_pipe.services.solver.coefficients import SLOPE_COEFFICIENT_MAX, slope_overflows
from opensolve_pipe.services.solver.elements import (
    PipeConnectionLaw,
    QuadraticLossLaw,
    ValveLaw,
)
from opensolve_pipe.services.solver.errors import TopologyError
from opensolve_pipe.services.solver.fittings import ResolvedFitting
from opensolve_pipe.services.solver.gga import solve_gga
from opensolve_pipe.services.solver.network import NORMAL, LinkLaw, LinkState
from opensolve_pipe.services.solver.orifice import (
    OrificeLaw,
    dk_dc,
    k_of_c,
    ratio_range,
    re_lo,
    refusal,
)
from opensolve_pipe.services.solver.status import active_state

from .helpers import (
    assigned_flow,
    connection,
    custom_fluid,
    custom_pipe,
    project_dict,
    reservoir,
    tee,
)

DIVERGED = "the iteration diverged (non-finite head loss)"
"""The message's start, unchanged (test_not_converged_flag asserts it too)."""
BOUND = sys.float_info.max / 2.0
"""Half the largest double: 2c is a finite double exactly up to here."""
NUM = r"(-?\d+(?:\.\d+)?(?:e[+-]\d+)?)"


def area(d: float) -> float:
    return 0.25 * math.pi * d**2


def element(ctype: str, cid: str, **kw: Any) -> dict[str, Any]:
    return {
        "type": ctype,
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "ports": [{"id": "inlet", "nominalSize": 0.1}, {"id": "outlet", "nominalSize": 0.1}],
        **kw,
    }


def line(
    *elements: dict[str, Any],
    d: float = 0.1,
    length: float = 10.0,
    fittings: list[dict[str, Any]] | None = None,
    max_iterations: int = 100,
    library: list[dict[str, Any]] | None = None,
    fluid: dict[str, Any] | None = None,
) -> Project:
    """R1 (level 10 m) -> L1 -> elements in series -> R2 (level 0 m), custom pipes of bore d
    (ε = 4.5e-5 m), water-like liquid (998 kg/m³, 1 mPa·s) unless ``fluid``; ``fittings`` on
    L1."""
    ids = [e["id"] for e in elements]
    ends = [("R1", "port_1"), *[p for i in ids for p in ((i, "inlet"), (i, "outlet"))]]
    ends.append(("R2", "port_1"))
    conns = [
        connection(
            f"L{n + 1}",
            ends[2 * n],
            ends[2 * n + 1],
            pipes=[custom_pipe(length, d, 4.5e-5)],
            fittings=fittings if n == 0 else None,
        )
        for n in range(len(ends) // 2)
    ]
    data = project_dict(
        [reservoir("R1", level=10.0), *elements, reservoir("R2", level=0.0)],
        conns,
        fluid=fluid or custom_fluid(),
        max_iterations=max_iterations,
    )
    if library is not None:
        data["resistanceLibrary"] = library
    return Project.model_validate(data)


def built(project: Project) -> BuiltNetwork:
    return build_network(project, fluid_properties(project.fluid))


def not_converged(state: SolvedState) -> Flag:
    assert not state.converged
    [flag] = [f for f in state.flags if f.code == "NOT_CONVERGED"]
    return flag


def refused(project: Project) -> Any:
    with pytest.raises(TopologyError) as caught:
        solve_project(project)
    [found] = caught.value.issues
    return found


def assert_quotes(message: str, unit: str, value: float) -> None:
    """The refusal quotes ``value`` and the bound with as many digits as tell them apart: the
    two texts differ, so the value read is above the bound read, each within its rounding."""
    quoted, bound = quoted_pair(message, unit)
    assert quoted == pytest.approx(value, rel=1e-14)
    assert bound == pytest.approx(BOUND, rel=1e-14)
    assert quoted > bound


def quoted_pair(message: str, unit: str) -> tuple[float, float]:
    """The coefficient and the bound a refusal quotes: '... of X <unit>, above Y <unit>, half
    the largest floating-point number' (an orifice plate's: 'of at least X')."""
    after = f" {re.escape(unit)}" if unit else ""
    match = re.search(
        rf"of (?:at least )?{NUM}{after}, above {NUM}{after}, half the largest floating-point "
        "number",
        message,
    )
    assert match is not None, message
    return float(match[1]), float(match[2])


# --------------------------------------------------------------------------- the bound


def test_the_slope_bound_is_half_the_largest_double() -> None:
    """2c is exact unless it overflows: finite up to the bound, infinite from the next double."""
    assert SLOPE_COEFFICIENT_MAX == BOUND
    assert sys.float_info.max == 2.0 * BOUND
    assert not slope_overflows(BOUND)
    assert slope_overflows(math.nextafter(BOUND, math.inf))
    assert not slope_overflows(math.inf)  # not finite: the finiteness tests' case, not this one
    # Each quadratic law's slope at the bound and one double past it, at 1 ft/s in 0.1 m.
    q = foot * area(0.1)
    assert math.isfinite(QuadraticLossLaw(BOUND).evaluate(q)[1])
    assert QuadraticLossLaw(math.nextafter(BOUND, math.inf)).evaluate(q)[1] == math.inf
    assert math.isnan(QuadraticLossLaw(math.nextafter(BOUND, math.inf)).evaluate(0.0)[1])


# --------------------------------------------------------------------------- (a) the GGA


def _huge_fitting(minor: float, d: float) -> ResolvedFitting:
    """One fitting whose n K/(2 g A²) on bore d is ``minor`` (K = minor · 2 g A², formed so that
    it does not overflow)."""
    k = 2.0 * g * area(d) ** 2 * minor
    return ResolvedFitting(
        index=0,
        type="gate_valve",
        quantity=1,
        k_forward=k,
        k_reverse=k,
        segment_forward=0,
        segment_reverse=0,
        correlation_forward="test",
        correlation_reverse="test",
        source="test",
        user_k=True,
        valid_in_laminar_flow=True,
        range_warning=None,
    )


@pytest.mark.parametrize("kind", ["valve", "equipment", "fittings", "orifice"])
def test_the_gga_names_the_law_whose_slope_is_not_finite(kind: str) -> None:
    """Each kind of quadratic law, given a c above the bound in place of its own (as the
    builder no longer lets one through), makes the first iterate's slope infinite: the message
    names that element, the flow (1 ft/s in its 0.1 m or 1 m inlet pipe) and its c. Before, the
    message was DIVERGED alone."""
    d = 1.0 if kind == "orifice" else 0.1
    c = 1.7e308
    if kind == "valve":
        project = line(element("valve", "X1", valveType="gate"), d=d)
    elif kind == "orifice":
        project = line(element("orifice", "X1", boreDiameter=0.5, dischargeCoefficient=0.6), d=d)
    else:
        project = line(element("equipment", "X1", rating={"kind": "Cv", "value": 90.0}), d=d)
    network = built(project).network
    states: list[LinkState] = [NORMAL] * len(network.links)
    law: LinkLaw
    if kind == "fittings":
        [k] = [ln.index for ln in network.links if ln.connection_id == "L1"]
        own = network.links[k].law
        assert isinstance(own, PipeConnectionLaw)
        law = PipeConnectionLaw(own.segments, [_huge_fitting(c, d)], "colebrook", g)
        named, what, value = "L1", "fittings' loss coefficient Σ n K/(2 g A²)", c
    else:
        [k] = [ln.index for ln in network.links if ln.component_id == "X1"]
        if kind == "valve":
            law = ValveLaw(2.0 * g * area(d) ** 2 * c, area(d), g)
            what, value = "loss coefficient K/(2 g A²)", c
        elif kind == "equipment":
            law = QuadraticLossLaw(c)
            what, value = "loss coefficient c", c
        else:
            # K = (S/(C β²) − 1)² with C 0.6 entered: β 1.2e-77 gives K ≈ 1.34e308, finite,
            # whose 2K overflows; K/(2 g A²) on 1 m is about 1.1e307.
            law = OrificeLaw(d, 1.2e-77, 998.0, 1.0e-3, 0.6, None, g)
            beta = 1.2e-77 / d
            k_plate = (1.0 / (0.6 * beta * beta) - 1.0) ** 2  # S = 1 to double precision
            what, value = "loss coefficient K/(2 g A²)", k_plate / (2.0 * g * area(d) ** 2)
        named = "X1"
    states[k] = LinkState(law=law)
    result = solve_gga(network, states, tolerance=1.0e-9, max_iterations=100)
    q0 = foot * area(d)
    assert not result.converged
    assert result.iterations == 0  # the first iterate
    [found] = result.nonfinite_laws
    assert (found.link, found.element_id, found.value) == (k, named, "slope dh/dQ")
    assert found.flow == pytest.approx(q0, rel=1e-15)
    assert found.coefficient == pytest.approx(value, rel=1e-12)
    assert found.coefficient_name == what
    assert result.message == (
        f"{DIVERGED}: not a finite number in the law of '{named}' (slope dh/dQ at a flow of "
        f"{q0:.3g} m³/s; {what} = {found.coefficient:.6g} s²/m⁵)"
    )


def test_two_laws_are_named_in_link_order_with_the_first_ones_numbers() -> None:
    """Two equipment items on 10 m pipes whose c Q0² overflows at the start flow (c 3.2e305 and
    4e305 > DBL_MAX/Q0², Q0 = 1 ft/s × 78.5 m² = 23.9 m³/s, about 3.14e305): their head losses
    are infinite, their slopes 2c Q0 finite. Both are named; the flag's details give both ids
    and the first one's flow and c."""
    d = 10.0
    q0 = foot * area(d)
    assert 3.2e305 * q0 * q0 == math.inf
    assert math.isfinite(2.0 * 3.2e305 * q0)
    ratings = []
    for c in (3.2e305, 4.0e305):
        # A rated point of c = h_r/Q_r²: 1e8 Pa on 1000 kg/m³ at Q_r = √(h_r/c).
        ratings.append({"kind": "point", "pressureLoss": 1.0e8, "flow": 0.0, "density": 1000.0})
        ratings[-1]["flow"] = math.sqrt(1.0e8 / (1000.0 * g) / c)
    e1 = element("equipment", "E1", rating=ratings[0])
    e2 = element("equipment", "E2", rating=ratings[1])
    state = solve_project(line(e1, e2, d=d))
    flag = not_converged(state)
    c1 = 1.0e8 / (1000.0 * g) / (ratings[0]["flow"] * ratings[0]["flow"])
    c2 = 1.0e8 / (1000.0 * g) / (ratings[1]["flow"] * ratings[1]["flow"])
    assert state.convergence.message == (
        f"{DIVERGED}: not a finite number in the laws of 'E1' (head loss at a flow of "
        f"{q0:.3g} m³/s; loss coefficient c = {c1:.6g} s²/m⁵) and 'E2' (head loss at a flow of "
        f"{q0:.3g} m³/s; loss coefficient c = {c2:.6g} s²/m⁵)"
    )
    assert flag.message == f"the solve did not converge: {state.convergence.message}"
    assert flag.component_id is None  # the whole network's
    assert flag.connection_id is None
    assert flag.details["nonFiniteLawAt"] == "E1, E2"
    assert flag.details["nonFiniteLawFlow"] == pytest.approx(q0, rel=1e-15)
    assert flag.details["nonFiniteLawCoefficient"] == pytest.approx(c1, rel=1e-15)


def test_an_orifice_plate_whose_loss_overflows_at_the_start_flow_is_named() -> None:
    """A plate on a 10 m pipe whose law multiplies K by the flow before 1/(2 g A²): K Q0²
    overflows (K ≈ 9.9e305, Q0 = 23.9 m³/s) though K/(2 g A²) Q0² does not, while its slope
    term 2K Q0 stays finite; the plate is named, with its K/(2 g A²) at that flow. (Not
    refused: its slope's 2K is finite.)"""
    d = 10.0
    q0 = foot * area(d)
    # Entered C 0.6, no taps: K = (S/(C β²) − 1)², S = √(1 − β⁴(1 − C²)) (ISO 5167-2).
    bore = 4.1e-76
    beta = bore / d
    s = math.sqrt(1.0 - beta**4 * (1.0 - 0.36))
    k_plate = (s / (0.6 * beta * beta) - 1.0) ** 2
    assert k_plate * q0 * q0 == math.inf
    assert math.isfinite(2.0 * k_plate * q0)
    plate = element("orifice", "O1", boreDiameter=bore, dischargeCoefficient=0.6)
    state = solve_project(line(plate, d=d))
    flag = not_converged(state)
    c = k_plate / (2.0 * g * area(d) ** 2)
    assert flag.details["nonFiniteLawAt"] == "O1"
    assert flag.details["nonFiniteLawFlow"] == pytest.approx(q0, rel=1e-15)
    assert flag.details["nonFiniteLawCoefficient"] == pytest.approx(c, rel=1e-12)
    assert state.convergence.message.startswith(
        f"{DIVERGED}: not a finite number in the law of 'O1' (head loss at a flow of "
        f"{q0:.3g} m³/s; loss coefficient K/(2 g A²) = "
    )


def test_pipes_at_a_runaway_flow_are_named() -> None:
    """test_not_converged_flag's project in a liquid of 1e-300 kg/m³: R1's head is about 1e307
    m and the second iterate's flows run away; both pipes' head losses are infinite there, and
    both are named (a pipe's friction has no single coefficient, so none is quoted)."""
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
    data = project_dict(
        [reservoir("R1", level=5.0, surface_pressure=1.0e8), pump, reservoir("R2", level=20.0)],
        [
            connection("P1", ("R1", "port_1"), ("PU1", "suction"), length=10.0),
            connection("P2", ("PU1", "discharge"), ("R2", "port_1"), length=50.0),
        ],
        fluid=custom_fluid(1.0e-300, 1.0e-300, vapor_pressure=1.0e8),
        pump_library=[curve],
    )
    state = solve_project(Project.model_validate(data))
    flag = not_converged(state)
    assert flag.details["nonFiniteLawAt"] == "P1, P2"
    assert "nonFiniteLawCoefficient" not in flag.details
    assert re.fullmatch(
        rf"{re.escape(DIVERGED)}: not a finite number in the laws of 'P1' \(head loss at a flow "
        rf"of {NUM} m³/s\) and 'P2' \(head loss at a flow of {NUM} m³/s\)",
        state.convergence.message,
    )


# --------------------------------------------------------------------------- (b) refusals


def _bits(x: float) -> int:
    return int(struct.unpack("<q", struct.pack("<d", x))[0])


def _double(bits: int) -> float:
    return float(struct.unpack("<d", struct.pack("<q", bits))[0])


def _adjacent(
    low: float, high: float, coefficient: Any, limit: float = BOUND
) -> tuple[float, float]:
    """(at, past): two adjacent positive doubles of an input on which ``coefficient`` decreases,
    at most ``limit`` at the first and above it at the second, found by bisection over the
    doubles between ``low`` (above the limit) and ``high`` (at most the limit); positive
    doubles are ordered as their bit patterns."""
    a, b = _bits(low), _bits(high)
    assert coefficient(low) > limit >= coefficient(high)
    while b - a > 1:
        middle = (a + b) // 2
        if coefficient(_double(middle)) > limit:
            a = middle
        else:
            b = middle
    at, past = _double(b), _double(a)
    assert past == math.nextafter(at, 0.0)
    assert coefficient(at) <= limit < coefficient(past)
    return at, past


def test_a_valve_at_the_slope_bound_solves_and_one_past_it_is_refused() -> None:
    """A gate valve rated by a Cv on a 0.1 m inlet pipe: c = Cv_to_K(Cv, D)/(2 g A²) (D9). At
    the largest c up to the bound the valve solves (Newton halves the flow from 1 ft/s towards
    √(10 m/c), so it needs about 500 iterations); at the next smaller Cv, c is past it and the
    valve is refused, named, quoting c and the bound."""
    d = 0.1

    def c_of(cv: float) -> float:
        return float(fluids.fittings.Cv_to_K(cv, d)) / (2.0 * g * area(d) * area(d))

    at, past = _adjacent(1.0e-151, 1.0e-149, c_of)
    gate = element("valve", "V1", valveType="gate", resistance={"kind": "Cv", "value": at})
    project = line(gate, max_iterations=1000)
    valve_law = built(project).valves["V1"].law
    assert isinstance(valve_law, ValveLaw)
    assert valve_law.coefficient == c_of(at)
    state = solve_project(project)
    assert state.converged, state.convergence.message
    gate["resistance"]["value"] = past
    found = refused(line(gate))
    assert (found.code, found.component_ids, found.connection_ids) == (
        "VALVE_RESISTANCE_OUT_OF_RANGE",
        ["V1"],
        [],
    )
    assert found.message.startswith(
        f"valve 'V1': a Cv of {past:g} on the inlet pipe's inner diameter of 0.1 m gives a loss "
        "coefficient K/(2 g A²) of "
    )
    assert found.message.endswith(
        ", half the largest floating-point number, so the slope of its head loss, "
        "2 K/(2 g A²) |Q|, is not a finite floating-point number at any flow; the solver "
        "cannot represent this valve"
    )
    assert_quotes(found.message, "s²/m⁵", c_of(past))


def test_an_isolated_valve_past_the_slope_bound_is_refused_though_never_evaluated() -> None:
    """D9: the refusal holds wherever the element is, as it does for a c that is not a finite
    double. Isolated, the gate valve's law is never evaluated: at the bound the line solves
    (method 1.6.0 solved it past the bound too); one Cv smaller it is refused, the change that
    makes this method 1.6.1."""
    d = 0.1

    def c_of(cv: float) -> float:
        return float(fluids.fittings.Cv_to_K(cv, d)) / (2.0 * g * area(d) * area(d))

    at, past = _adjacent(1.0e-151, 1.0e-149, c_of)
    gate = element(
        "valve", "V1", valveType="gate", resistance={"kind": "Cv", "value": at}, status="isolated"
    )
    state = solve_project(line(gate))
    assert state.converged, state.convergence.message
    gate["resistance"]["value"] = past
    found = refused(line(gate))
    assert (found.code, found.component_ids, found.connection_ids) == (
        "VALVE_RESISTANCE_OUT_OF_RANGE",
        ["V1"],
        [],
    )
    assert_quotes(found.message, "s²/m⁵", c_of(past))


def test_a_valve_on_a_library_entry_past_the_slope_bound_is_refused() -> None:
    """The entry form (D22): a K of 1e7 stated at a bore d₀ on a 0.1 m inlet pipe, K = K₀
    (D/d₀)⁴, c = K/(2 g A²) about 1.69e308."""
    d = 0.1
    d0 = d * (1.0e7 / (2.0 * g * area(d) ** 2 * 1.69e308)) ** 0.25
    entry = {"id": "RS1", "name": "huge", "source": "test", "kind": "K", "value": 1.0e7}
    entry["referenceDiameter"] = d0
    gate = element("valve", "V1", valveType="gate", resistance={"kind": "library", "id": "RS1"})
    found = refused(line(gate, library=[entry]))
    assert found.code == "VALVE_RESISTANCE_OUT_OF_RANGE"
    assert found.message.startswith(
        f"valve 'V1': its project library resistance entry 'RS1', K 1e+07 at {d0:g} m, on the "
        "inlet pipe's inner diameter of 0.1 m gives a loss coefficient K/(2 g A²) of "
    )
    value, bound = quoted_pair(found.message, "s²/m⁵")
    # Far from the bound, both to 6 significant digits.
    assert value == pytest.approx(1.69e308, rel=1e-6)
    assert f"{bound:.6g}" == "8.98847e+307" == f"{BOUND:.6g}"


def test_equipment_at_the_slope_bound_solves_and_one_past_it_is_refused() -> None:
    """A rated point, c = (ΔP_r/(ρ_r g))/Q_r² (D18): at the largest c up to the bound it solves;
    at the next smaller Q_r it is refused, quoting c and the bound."""
    head = 1.0e8 / (1000.0 * g)

    def c_of(q: float) -> float:
        return head / (q * q)

    estimate = math.sqrt(head / BOUND)
    at, past = _adjacent(0.5 * estimate, 2.0 * estimate, c_of)
    rating = {"kind": "point", "pressureLoss": 1.0e8, "flow": at, "density": 1000.0}
    item = element("equipment", "E1", rating=rating)
    project = line(item, max_iterations=1000)
    assert built(project).equipment["E1"].law.coefficient == c_of(at)
    state = solve_project(project)
    assert state.converged, state.convergence.message
    rating["flow"] = past
    found = refused(line(item))
    assert (found.code, found.component_ids) == ("EQUIPMENT_RATING_OUT_OF_RANGE", ["E1"])
    assert found.message.startswith(
        f"equipment 'E1': a rating of 1e+08 Pa at {past:g} m³/s for a fluid of 1000 kg/m³ gives "
        "a loss coefficient, c = ΔP_r/(ρ_r g Q_r²), of "
    )
    assert found.message.endswith(
        ", half the largest floating-point number, so the slope of its head loss, 2c|Q|, is "
        "not a finite floating-point number at any flow; the solver cannot represent this "
        "element"
    )
    assert_quotes(found.message, "s²/m⁵", c_of(past))


def _entry_fittings(count: int, d0: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    entry = {"id": "RS1", "name": "huge", "source": "test", "kind": "K", "value": 1.0e7}
    entry["referenceDiameter"] = d0
    fitting = {"type": "gate_valve", "quantity": 1, "pipeIndex": 0, "resistanceId": "RS1"}
    return [entry], [dict(fitting) for _ in range(count)]


def test_a_fitting_entry_at_the_slope_bound_solves_and_one_past_it_is_refused() -> None:
    """A fitting on a K entry of 1e7 stated at d₀, on a 0.1 m pipe: n K₀ (D/d₀)⁴/(2 g A²)
    (D22). At the bound the connection solves; at the next smaller d₀ its c is past it and the
    fitting is refused, named by connection and number."""
    d = 0.1

    def c_of(d0: float) -> float:
        return 1.0e7 * (d / d0) ** 4 / (2.0 * g * area(d) ** 2)

    estimate = d * (1.0e7 / (2.0 * g * area(d) ** 2 * BOUND)) ** 0.25
    d0, past = _adjacent(0.5 * estimate, 2.0 * estimate, c_of)
    library, fittings = _entry_fittings(1, d0)
    project = line(fittings=fittings, library=library, max_iterations=1000)
    law = built(project).connections["L1"].law
    assert isinstance(law, PipeConnectionLaw)
    assert law.minor_coefficient(1.0) == c_of(d0)
    state = solve_project(project)
    assert state.converged, state.convergence.message
    library, fittings = _entry_fittings(1, past)
    found = refused(line(fittings=fittings, library=library))
    assert (found.code, found.connection_ids) == ("FITTING_RESISTANCE_OUT_OF_RANGE", ["L1"])
    assert found.message.startswith(
        f"connection 'L1' fitting 1 (gate_valve): its project library resistance entry 'RS1', "
        f"K 1e+07 at {past:g} m, on the inner diameter of pipe 1, 0.1 m, gives a loss "
        "coefficient n K/(2 g A²) of "
    )
    assert found.message.endswith(
        ", half the largest floating-point number, so the slope of the connection's head loss, "
        "which takes 2 n K/(2 g A²) |Q| from it, is not a finite floating-point number at any "
        "flow; the solver cannot represent this fitting"
    )
    assert_quotes(found.message, "s²/m⁵", c_of(past))


def test_two_fittings_whose_sum_passes_the_slope_bound_are_refused_on_the_connection() -> None:
    """Two fittings on one entry, each within the bound: their sum, 2 n K/(2 g A²) exactly, is
    at most the bound at d₀ and past it at the next smaller d₀ (the law's slope takes 2 Σ)."""
    d = 0.1

    def c_of(d0: float) -> float:
        return 1.0e7 * (d / d0) ** 4 / (2.0 * g * area(d) ** 2)

    half = BOUND / 2.0
    estimate = d * (1.0e7 / (2.0 * g * area(d) ** 2 * half)) ** 0.25
    d0, past = _adjacent(0.5 * estimate, 2.0 * estimate, c_of, half)
    library, fittings = _entry_fittings(2, d0)
    project = line(fittings=fittings, library=library, max_iterations=1000)
    law = built(project).connections["L1"].law
    assert isinstance(law, PipeConnectionLaw)
    assert law.minor_coefficient(1.0) == 2.0 * c_of(d0) <= BOUND
    assert solve_project(project).converged
    library, fittings = _entry_fittings(2, past)
    found = refused(line(fittings=fittings, library=library))
    assert (found.code, found.connection_ids) == ("FITTING_RESISTANCE_OUT_OF_RANGE", ["L1"])
    total = 2.0 * c_of(past)
    match = re.fullmatch(
        rf"connection 'L1': its fittings' loss coefficients n K/\(2 g A²\) are each finite, but "
        rf"their sum for flow from → to, {NUM} s²/m⁵, is above {NUM} s²/m⁵, half the largest "
        r"floating-point number, so the slope of the connection's head loss, which takes "
        r"2 Σ n K/\(2 g A²\) \|Q\| from them, is not a finite floating-point number at any flow "
        r"\(on project library resistance entries: fitting 1 \(gate_valve\) on 'RS1', fitting 2 "
        r"\(gate_valve\) on 'RS1'\); the solver cannot represent this connection",
        found.message,
    )
    assert match is not None, found.message
    assert float(match[1]) == pytest.approx(total, rel=1e-14)
    assert float(match[2]) == pytest.approx(BOUND, rel=1e-14)
    assert float(match[1]) > float(match[2])


def test_an_orifice_plate_at_the_slope_bound_is_accepted_and_one_past_it_refused() -> None:
    """An entered C of 0.6 without taps on a 1 m pipe (D20): C_L = C at every flow, K = (S/(C
    β²) − 1)². At the largest K up to the bound the plate builds and solves (its K/(2 g A²),
    about 7.4e306, is finite); at the next smaller bore its K is past the bound, so the slope
    2 K|Q|/(2 g A²) is infinite at every flow but zero, and decision 17's rule (d) refuses it."""
    d = 1.0

    def k_of(bore: float) -> float:
        beta = bore / d
        s = math.sqrt(1.0 - beta**4 * (1.0 - 0.36))
        u = s / (0.6 * beta * beta) - 1.0
        return u * u  # inf past the largest double (** would raise)

    # The boundary is the solver's own double (its K, written without cancellation as β → 1,
    # can differ from this form in the last bits): found with orifice.k_of_c, and checked
    # against the form above.
    at, past = _adjacent(1.0e-77, 2.0e-77, lambda bore: k_of_c(d, bore, 0.6))
    assert k_of_c(d, at, 0.6) == pytest.approx(k_of(at), rel=1e-15)
    plate = element("orifice", "O1", boreDiameter=at, dischargeCoefficient=0.6)
    project = line(plate, d=d, max_iterations=1000)
    law = built(project).orifices["O1"].law
    assert law.low_k == k_of_c(d, at, 0.6)
    assert not slope_overflows(law.low_k)
    state = solve_project(project)
    assert state.converged, state.convergence.message
    plate["boreDiameter"] = past
    found = refused(line(plate, d=d))
    assert (found.code, found.component_ids) == ("ORIFICE_OUT_OF_RANGE", ["O1"])
    assert found.message.startswith(
        f"orifice 'O1': a bore diameter of {past:g} m in an inlet pipe of inner diameter 1 m "
        f"(β = d/D = {past:.6g}): with a discharge coefficient of at most 0.6 at every flow it "
        "gives a loss coefficient K of at least "
    )
    assert found.message.endswith(
        ", half the largest floating-point number, so the slope of its head loss, "
        "2 K|Q|/(2 g A²), is not a finite floating-point number at any flow but zero; the "
        "solver cannot represent this plate"
    )
    assert_quotes(found.message, "", k_of(past))


# An entered C at corner or flange taps is moved to D and D/2 tappings by ISO's ratio r (D20,
# decision 13): C_L = C_e r(Re_eff), held at C_e r(Re_lo) below Re_lo (5000 here), r within
# the closed-form bounds [r_min, r_max] of ``orifice.ratio_range``. Rule (d) takes K at
# C_e r_max, a lower bound of every K the law takes; K at C_e r_min, below every C the law takes,
# can be past the slope bound on a plate whose law never forms an infinite 2K.
MOVED_D, MOVED_BORE = 1.0, 0.5
VISCOUS = (1000.0, 10.0)
"""kg/m³, Pa·s: Re_D = 4ρ|Q|/(π D μ) is 127 per m³/s on 1 m, so Re_lo, 5000, is at 39 m³/s,
far above the line's flows from its start, 1 ft/s (0.24 m³/s), down: C_L is held."""


def _moved_plate(taps: OrificeTaps) -> tuple[float, float, float]:
    """(C_e, r_min, r_max): the smallest entered C at ``taps`` whose K at the held C_L, the law's
    own ``low_k`` in the ``VISCOUS`` liquid, is within the slope bound (by bisection over the
    doubles), and the move's bounds at the plate."""
    d, bore = MOVED_D, MOVED_BORE
    beta = bore / d
    # K = u² ≈ (1 − β⁴)/(C β²)² while C β² ≪ S (k_of_c), so K is the bound near this C.
    estimate = math.sqrt((1.0 - beta**4) / (beta**4 * BOUND))

    def low_k(entered: float) -> float:
        return OrificeLaw(d, bore, *VISCOUS, entered, taps, g).low_k

    entered, _ = _adjacent(0.5 * estimate, 2.0 * estimate, low_k)
    r_min, r_max = ratio_range(d, bore, taps, re_lo(beta, d, "d_and_d_2"))
    return entered, r_min, r_max


def _moved_line(entered: float, taps: OrificeTaps, fluid: tuple[float, float]) -> Project:
    plate = element(
        "orifice", "O1", boreDiameter=MOVED_BORE, dischargeCoefficient=entered, taps=taps
    )
    return line(plate, d=MOVED_D, max_iterations=1000, fluid=custom_fluid(*fluid))


@pytest.mark.parametrize("taps", ["flange", "corner"])
def test_a_moved_c_past_the_slope_bound_only_below_every_c_the_law_takes_solves(
    taps: OrificeTaps,
) -> None:
    """D = 1 m, bore 0.5 m, an entered C_e at flange or corner taps, the smallest whose held K
    is within the slope bound: K at C_e r_min is past it, but every C the law takes is at least
    the held C_e r(Re_lo) (r is above r(Re_lo) at every Re_D sampled, to 1e20), so K at every
    flow is within it. Rule (d), taken at C_e r_max, accepts the plate (taken at C_e r_min it
    would refuse a plate whose 2K is finite at every flow); in the viscous liquid the line
    solves (Newton halves the flow from 1 ft/s, about 500 iterations), as 7fcbdb8 solved it."""
    d, bore = MOVED_D, MOVED_BORE
    entered, r_min, r_max = _moved_plate(taps)
    assert slope_overflows(k_of_c(d, bore, entered * r_min))
    assert not slope_overflows(k_of_c(d, bore, entered * r_max))
    assert refusal(d, bore, entered, taps, g) is None
    project = _moved_line(entered, taps, VISCOUS)
    law = built(project).orifices["O1"].law
    assert law.low_ratio is not None
    assert r_min < law.low_ratio < r_max
    assert law.low_k == k_of_c(d, bore, entered * law.low_ratio)
    assert not slope_overflows(law.low_k)
    per_flow = 4.0 * VISCOUS[0] / (math.pi * d * VISCOUS[1])  # Re_D per m³/s
    for reynolds in (1.001 * law.re_lo, *(10.0**n for n in range(4, 21))):
        at = law.state(reynolds / per_flow)
        assert at.coefficient_reynolds is not None
        assert at.coefficient_reynolds > law.re_lo
        assert at.loss_c >= law.low_c
        assert at.k <= law.low_k
    state = solve_project(project)
    assert state.converged, state.convergence.message


@pytest.mark.parametrize("taps", ["flange", "corner"])
def test_a_moved_c_whose_k_at_its_largest_c_passes_the_slope_bound_is_refused(
    taps: OrificeTaps,
) -> None:
    """The same plate: every C the law takes is at most C_e r_max, so K there is at most every K
    it takes, and rule (d) refuses the plate whose K at C_e r_max is past the slope bound, quoting
    C_e r_max: its slope is not finite at any flow but zero. Found by bisection over C_e: at the
    largest K at C_e r_max up to the bound the plate builds, at the next smaller C_e it is
    refused. r_max is 1 here (eq. (4)'s tap difference ΔC = C(D and D/2) − C(taps) is at most
    0 at Re_lo and as Re → ∞, and the bound takes max(ΔC, 0)), above every r the law takes, so
    the plate that builds has its held K past the bound too: in the viscous liquid its line
    stops at the first iterate, naming the plate (D7). On 7fcbdb8, which had no slope bound,
    both were a 200 NOT_CONVERGED whose message named nothing."""
    d, bore = MOVED_D, MOVED_BORE
    _, r_min, r_max = _moved_plate(taps)
    assert r_max == 1.0
    assert r_min < 1.0

    def k_high(entered: float) -> float:
        return k_of_c(d, bore, entered * r_max)

    estimate = math.sqrt((1.0 - (bore / d) ** 4) / ((bore / d) ** 4 * BOUND))
    at, past = _adjacent(0.5 * estimate, 2.0 * estimate, k_high)
    assert refusal(d, bore, at, taps, g) is None
    project = _moved_line(at, taps, VISCOUS)
    assert slope_overflows(built(project).orifices["O1"].law.low_k)
    flag = not_converged(solve_project(project))
    assert flag.details["nonFiniteLawAt"] == "O1"
    q0 = foot * area(d)
    assert flag.message.startswith(
        f"the solve did not converge: {DIVERGED}: not a finite number in the law of 'O1' "
        f"(slope dh/dQ at a flow of {q0:.3g} m³/s; "
    )
    found = refused(_moved_line(past, taps, VISCOUS))
    assert (found.code, found.component_ids) == ("ORIFICE_OUT_OF_RANGE", ["O1"])
    assert found.message.startswith(
        "orifice 'O1': a bore diameter of 0.5 m in an inlet pipe of inner diameter 1 m "
        f"(β = d/D = 0.5): with a discharge coefficient of at most {past * r_max:.6g} at every "
        "flow it gives a loss coefficient K of at least "
    )
    assert found.message.endswith(
        ", half the largest floating-point number, so the slope of its head loss, "
        "2 K|Q|/(2 g A²), is not a finite floating-point number at any flow but zero; the "
        "solver cannot represent this plate"
    )
    assert_quotes(found.message, "", k_high(past))


@pytest.mark.parametrize("taps", ["flange", "corner"])
def test_a_moved_c_whose_slope_overflows_above_re_lo_is_named(taps: OrificeTaps) -> None:
    """The accepted plate (``_moved_plate``) in a water-like liquid (1000 kg/m³, 1 mPa·s): the
    start flow, 1 ft/s in the 1 m pipe, is at Re_D about 3e5, above Re_lo, where C_L follows
    eq. (4). K there is within the slope bound (C_L is above the held C), but the slope's other
    term is not finite: dK/dC = −2K(1/C + β²/S), with K about 9e307 and 1/C about 2.4e153, is
    −inf. The plate is not refused (its slope is finite below Re_lo, at every flow
    of the viscous case); this flow-dependent overflow stops the iteration at its first iterate
    and the message names the plate with its K/(2 g A²) there (D7). 7fcbdb8 stopped there too,
    naming nothing."""
    d, bore = MOVED_D, MOVED_BORE
    entered, _, _ = _moved_plate(taps)
    project = _moved_line(entered, taps, (1000.0, 1.0e-3))
    law = built(project).orifices["O1"].law
    q0 = foot * area(d)
    at = law.state(q0)
    assert at.reynolds > law.re_lo
    assert not slope_overflows(at.k)
    assert dk_dc(d, bore, at.loss_c, at.k) == -math.inf
    h, slope = law.evaluate(q0)
    assert math.isfinite(h)
    assert not math.isfinite(slope)
    state = solve_project(project)
    flag = not_converged(state)
    assert flag.details["nonFiniteLawAt"] == "O1"
    assert flag.details["nonFiniteLawFlow"] == pytest.approx(q0, rel=1e-15)
    c = flag.details["nonFiniteLawCoefficient"]
    assert c == pytest.approx(at.k / (2.0 * g * area(d) ** 2), rel=1e-12)
    assert state.convergence.message == (
        f"{DIVERGED}: not a finite number in the law of 'O1' (slope dh/dQ at a flow of "
        f"{q0:.3g} m³/s; loss coefficient K/(2 g A²) = {c:.6g} s²/m⁵)"
    )


def test_a_goal_seek_bound_past_the_orifice_slope_bound_is_a_400_without_values() -> None:
    """D16/D20: the network is built at each bound of a plate's bore; at a bore whose K is past
    the slope bound the 400 says so, located by index, with no id or value."""
    from opensolve_pipe.models.api import GoalSeekRequest
    from opensolve_pipe.services import goal_seek as gs

    d = 1.0
    plate = element("orifice", "O1", boreDiameter=0.5, dischargeCoefficient=0.6)
    project = line(plate, d=d).model_dump(by_alias=True, exclude_unset=True)
    request = GoalSeekRequest.model_validate(
        {
            "project": project,
            "variables": [
                {
                    "kind": "component",
                    "componentId": "O1",
                    "field": "boreDiameter",
                    "lower": 1.25e-77,
                    "upper": 0.5,
                }
            ],
            "goals": [{"quantity": "orifice_flow", "elementId": "O1", "target": 0.5}],
        }
    )
    with pytest.raises(gs.GoalSeekInputError) as caught:
        gs.prepare(request)
    [issue] = caught.value.issues
    assert (issue.code, issue.component_ids) == ("ORIFICE_OUT_OF_RANGE", ["O1"])
    assert issue.message == (
        "body.variables.0.lower: the orifice's loss coefficient K is above half the largest "
        "floating-point number at this bore, so the slope of its head loss is not a finite "
        "floating-point number"
    )


# --------------------------------------------------------------------------- pipes


def test_a_pipe_whose_reynolds_denominator_underflows_is_refused_not_a_500() -> None:
    """A 1e-11 m bore in a custom fluid of 1e-300 Pa·s at 1000 kg/m³: A ν = 7.85e-23 × 1e-303
    underflows to 0, and Re = |Q| D/(A ν) divided by zero (ZeroDivisionError, an internal error).
    1e-10 m (A ν subnormal, not 0) still solves."""
    fluid = custom_fluid(1000.0, 1.0e-300)
    for d, refuse in ((1.0e-11, True), (1.0e-10, False)):
        nu = 1.0e-300 / 1000.0
        assert (area(d) * nu == 0.0) is refuse
        data = project_dict(
            [reservoir("R1", level=10.0), reservoir("R2", level=0.0)],
            [connection("L1", ("R1", "port_1"), ("R2", "port_1"), pipes=[custom_pipe(1.0, d, 0)])],
            fluid=fluid,
        )
        project = Project.model_validate(data)
        if not refuse:
            assert solve_project(project).converged
            continue
        found = refused(project)
        assert (found.code, found.connection_ids) == ("PIPE_SIZE_OUT_OF_RANGE", ["L1"])
        assert found.message == (
            f"connection 'L1' pipe 1: an inner diameter of 1e-11 m with the fluid's kinematic "
            f"viscosity of {nu:g} m²/s gives a Reynolds number |Q| D/(A ν) whose denominator "
            "A ν is 0 in floating point (it underflows); the solver cannot represent this pipe"
        )


# --------------------------------------------------------------------------- fluids at the bounds
# A custom fluid's density and viscosity are any positive doubles up to 3e4 kg/m³ and 1e3 Pa·s
# (schema), so one at the bottom of that range makes some of the laws' arithmetic underflow or
# overflow before any flow is solved. Each case below was an internal error (500) on 7fcbdb8
# (the finisher's probe of fluids and sizes at the schema's bounds, 2026-11-03), but the
# closed-off plate, which solved there.

PLATE_HEAD = (
    "orifice 'O1': a bore diameter of 0.05 m in an inlet pipe of inner diameter 0.1 m "
    "(β = d/D = 0.5): "
)


def _plate(**kw: Any) -> dict[str, Any]:
    return element("orifice", "O1", boreDiameter=0.05, **kw)


@pytest.mark.parametrize("entered", [None, 0.6], ids=["iso", "entered"])
def test_a_plate_whose_reynolds_denominator_underflows_is_refused(entered: float | None) -> None:
    """μ = 5e-324 Pa·s (the smallest double) on a 0.1 m pipe: π D μ is 0, and the plate's law
    divided by it when it was built (ZeroDivisionError). The pipes are not refused (ρ = 1e-300
    kg/m³ makes ν = μ/ρ about 4.9e-24 m²/s, and A ν is not 0). Every plate, ISO's C or an
    entered one, since every plate's law computes Re_D."""
    rho, mu = 1.0e-300, 5e-324
    assert math.pi * 0.1 * mu == 0.0
    assert area(0.1) * (mu / rho) > 0.0
    plate = _plate() if entered is None else _plate(dischargeCoefficient=entered)
    found = refused(line(plate, fluid=custom_fluid(rho, mu)))
    assert (found.code, found.component_ids) == ("ORIFICE_OUT_OF_RANGE", ["O1"])
    assert found.message == (
        f"{PLATE_HEAD}with the fluid's dynamic viscosity of {mu:g} Pa·s, the denominator π D μ "
        "of its Reynolds number Re_D = 4ρ|Q|/(π D μ) is 0 in floating point (it underflows); "
        "the solver cannot represent this plate"
    )


def test_a_plate_on_iso_c_whose_area_times_density_underflows_is_refused() -> None:
    """ρ = 5e-324 kg/m³: fluids evaluates ISO 5167-2's C from the mass flow, v = m/(A ρ), and
    (π D²/4) ρ is 0 (ZeroDivisionError in fluids). An entered C is used as entered and never
    calls fluids, so that plate solves."""
    rho, mu = 5e-324, 1.0e-300
    assert 0.25 * math.pi * 0.1 * 0.1 * rho == 0.0
    fluid = custom_fluid(rho, mu)
    found = refused(line(_plate(), fluid=fluid))
    assert (found.code, found.component_ids) == ("ORIFICE_OUT_OF_RANGE", ["O1"])
    assert found.message == (
        f"{PLATE_HEAD}ISO 5167-2's discharge coefficient is evaluated (fluids) from the mass flow, "
        "dividing by the pipe's area times the fluid's density, (π D²/4) ρ, which with a "
        f"density of {rho:g} kg/m³ is 0 in floating point (it underflows); the solver cannot "
        "represent this plate"
    )
    assert solve_project(line(_plate(dischargeCoefficient=0.6), fluid=fluid)).converged


@pytest.mark.parametrize("taps", [None, "flange"], ids=["iso", "entered-at-flange-taps"])
def test_a_plate_whose_reynolds_number_is_infinite_at_every_flow_is_refused(
    taps: str | None,
) -> None:
    """ρ = 1000 kg/m³, μ = 1e-307 Pa·s on 0.1 m: 4ρ/(π D μ) overflows, so Re_D is infinite at
    every flow but zero, where fluids' ISO 5167-2 C takes log10(3700/Re_D) of 0 (ValueError).
    Refused wherever eq. (4) is used: ISO's C, and an entered C at flange taps (moved by ISO's
    ratio). An entered C without taps is not refused: it solves, here to the pipes' own
    divergence (ν = 1e-310 m²/s makes their Re infinite too), which names them."""
    rho, mu = 1000.0, 1.0e-307
    assert 4.0 * rho / (math.pi * 0.1 * mu) == math.inf
    fluid = custom_fluid(rho, mu)
    plate = _plate() if taps is None else _plate(dischargeCoefficient=0.6, taps=taps)
    found = refused(line(plate, fluid=fluid))
    assert (found.code, found.component_ids) == ("ORIFICE_OUT_OF_RANGE", ["O1"])
    assert found.message == (
        f"{PLATE_HEAD}with the fluid's density of {rho:g} kg/m³ and dynamic viscosity of {mu:g} "
        "Pa·s, its Reynolds number per unit flow, 4ρ/(π D μ), is not a finite floating-point "
        "number, so Re_D is infinite at every flow but zero, where ISO 5167-2's discharge "
        "coefficient cannot be evaluated; the solver cannot represent this plate"
    )
    state = solve_project(line(_plate(dischargeCoefficient=0.6), fluid=fluid))
    assert not_converged(state).details["nonFiniteLawAt"] == "L1, L2"


def test_a_closed_off_plate_with_an_infinite_reynolds_number_is_refused() -> None:
    """D9, D20 rule (e): R1 → R2 through a 0.1 m pipe, and a branch R1 → V1 → O1 → V2 → R2 whose
    gate valves are isolated, so the solve never evaluates the plate (ISO's C, a 0.5 mm bore on
    a 1 mm inlet pipe). In a liquid of 1000 kg/m³ and 5e-303 Pa·s the plate's Reynolds number
    per unit flow, 4ρ/(π D μ), overflows on 1 mm (on 0.1 m it is about 2.5e306, finite). With
    an active gate valve in the plate's place the project solves; with the plate, which rules
    (a) to (d) accept, rule (e) refuses it wherever it is, as the slope bound refuses an
    isolated valve. 7fcbdb8 solved it (converged, as with the gate): a 200 then, a 422 now."""
    rho, mu = 1000.0, 5.0e-303
    assert 4.0 * rho / (math.pi * 1.0e-3 * mu) == math.inf
    assert math.isfinite(4.0 * rho / (math.pi * 0.1 * mu))
    assert refusal(1.0e-3, 5.0e-4, None, None, g) is None

    def project(middle: dict[str, Any]) -> Project:
        small = [custom_pipe(1.0, 1.0e-3, 0.0)]
        data = project_dict(
            [
                reservoir("R1", level=10.0, ports=("port_1", "port_2")),
                element("valve", "V1", valveType="gate", status="isolated"),
                middle,
                element("valve", "V2", valveType="gate", status="isolated"),
                reservoir("R2", level=0.0, ports=("port_1", "port_2")),
            ],
            [
                connection("L1", ("R1", "port_1"), ("R2", "port_1"), length=10.0),
                connection("L2", ("R1", "port_2"), ("V1", "inlet"), length=10.0),
                connection("L3", ("V1", "outlet"), (middle["id"], "inlet"), pipes=small),
                connection("L4", (middle["id"], "outlet"), ("V2", "inlet"), length=10.0),
                connection("L5", ("V2", "outlet"), ("R2", "port_2"), length=10.0),
            ],
            fluid=custom_fluid(rho, mu),
        )
        return Project.model_validate(data)

    state = solve_project(project(element("valve", "V3", valveType="gate")))
    assert state.converged, state.convergence.message
    found = refused(project(element("orifice", "O1", boreDiameter=5.0e-4)))
    assert (found.code, found.component_ids) == ("ORIFICE_OUT_OF_RANGE", ["O1"])
    assert found.message == (
        "orifice 'O1': a bore diameter of 0.0005 m in an inlet pipe of inner diameter 0.001 m "
        f"(β = d/D = 0.5): with the fluid's density of {rho:g} kg/m³ and dynamic viscosity of "
        f"{mu:g} Pa·s, its Reynolds number per unit flow, 4ρ/(π D μ), is not a finite "
        "floating-point number, so Re_D is infinite at every flow but zero, where ISO 5167-2's "
        "discharge coefficient cannot be evaluated; the solver cannot represent this plate"
    )


def test_a_law_that_raises_in_the_iteration_is_named() -> None:
    """A 1 mm pipe in a liquid of 3e4 kg/m³ and 1e-307 Pa·s: ν = 3.3e-312 m²/s, so at the
    start flow, 1 ft/s, Re = v D/ν is about 9.1e307, where fluids' Clamond overflows inside and
    raises ValueError (math domain error). The iteration stops at its first iterate and names
    the pipe, with the exception's name (an internal error, 500, before)."""
    rho, mu, d = 3.0e4, 1.0e-307, 1.0e-3
    re = foot * d / (mu / rho)
    assert 9.0e307 < re < sys.float_info.max
    with pytest.raises(ValueError, match="math domain error"):
        fluids.friction.Clamond(re, 4.5e-5 / d)
    state = solve_project(line(d=d, fluid=custom_fluid(rho, mu)))
    flag = not_converged(state)
    q0 = foot * area(d)
    assert state.convergence.message == (
        f"{DIVERGED}: not a finite number in the law of 'L1' (head loss and slope dh/dQ, whose "
        f"computation raised ValueError, at a flow of {q0:.3g} m³/s)"
    )
    assert flag.details["nonFiniteLawAt"] == "L1"
    assert flag.details["nonFiniteLawFlow"] == pytest.approx(q0, rel=1e-15)
    assert "nonFiniteLawCoefficient" not in flag.details


def test_a_trace_velocity_head_that_overflows_is_left_out() -> None:
    """R1 at 1e5 Pa in a liquid of 1e-300 kg/m³ and 1e3 Pa·s, through three pipes 1e-300 m long
    and a tee: R1's head is p/(ρ g), about 1e304 m, the pipes are laminar (ν = 1e303 m²/s) and
    the solve converges with velocities above 1.34e154 m/s, whose square overflows. The tee's
    trace raised OverflowError on v_c**2 (500); its velocity head is now left out, as every
    trace value that is not a finite number is."""
    pipe = [custom_pipe(1.0e-300, 0.1, 0.0)]
    data = project_dict(
        [
            reservoir("R1", level=10.0, surface_pressure=1.0e5),
            tee("T1"),
            reservoir("R2", level=0.0),
            reservoir("R3", level=0.0),
        ],
        [
            connection("L1", ("R1", "port_1"), ("T1", "run_inlet"), pipes=pipe),
            connection("L2", ("T1", "run_outlet"), ("R2", "port_1"), pipes=pipe),
            connection("L3", ("T1", "branch"), ("R3", "port_1"), pipes=pipe),
        ],
        fluid=custom_fluid(1.0e-300, 1.0e3),
    )
    state = solve_project(Project.model_validate(data))
    assert state.converged
    values = {v.name: v.value for v in state.trace.elements["T1"].intermediates}
    v_c = values["Reference velocity v_c"]
    assert isinstance(v_c, float)
    with pytest.raises(OverflowError):
        _ = v_c**2
    assert "Velocity head v_c²/(2g)" not in values


# --------------------------------------------------------------------------- head offset, held head


def test_a_branch_leg_whose_head_offset_is_not_finite_is_named() -> None:
    """A Crane tee between two reservoirs at 5 m, its branch to an assigned flow of 9 L/s,
    every pipe 0.1023 m bore and 1e-300 m long, in a liquid of 1e-300 kg/m³ and 1e3 Pa·s (ν =
    1e303 m²/s): the first inner solve treats the legs as ideal (constant offsets) and converges;
    the branch-loss update then gives the run legs an own-flow coefficient K/(2 g A²) that is
    not finite, so their offset at the next solve's first iterate is not either. The final
    message names the tee once (its two legs are one element) with the flow its offset is taken
    at, each run leg's: by symmetry each reservoir supplies half the demand, −4.5 L/s (drawn
    from the tee's center). Found by the finisher's probe (4 projects of 37,170 end so)."""
    pipe = [custom_pipe(1.0e-300, 0.1023, 4.5e-5)]
    data = project_dict(
        [
            reservoir("R1", level=5.0),
            tee("T1", loss_model="crane"),
            reservoir("R2", level=5.0),
            assigned_flow("AF1", 0.009),
        ],
        [
            connection("L1", ("R1", "port_1"), ("T1", "run_inlet"), pipes=pipe),
            connection("L2", ("T1", "run_outlet"), ("R2", "port_1"), pipes=pipe),
            connection("L3", ("T1", "branch"), ("AF1", "port_1"), pipes=pipe),
        ],
        fluid=custom_fluid(1.0e-300, 1.0e3),
    )
    state = solve_project(Project.model_validate(data))
    flag = not_converged(state)
    assert flag.details["nonFiniteLawAt"] == "T1"
    assert flag.details["nonFiniteLawFlow"] == pytest.approx(-0.0045, rel=1e-9)
    assert "nonFiniteLawCoefficient" not in flag.details
    assert state.convergence.message.startswith(
        f"{DIVERGED}: not a finite number in the law of 'T1' (head offset at a flow of "
        f"{-0.0045:.3g} m³/s)"
    )


def test_an_active_prv_whose_held_head_is_not_finite_is_named() -> None:
    """A PRV with a setpoint of 1e8 Pa in a liquid of 5e-302 kg/m³: the head it holds, z +
    p_set/(ρ g) = 1e8/(5e-302 × 9.80665) m, overflows. The inner solve with the valve active
    (its initial status) stops at its first iterate naming the valve's held head, at the flow
    it is taken at, its outlet pipe's (1 ft/s in 0.1 m). The outer loop then opens the valve
    (its upstream head is below that setpoint), so the case converges: in the finisher's probe
    (37,170 projects) 352 inner solves named a held head, and no final message did."""
    rho = 5.0e-302
    assert 1.0e8 / (rho * g) == math.inf
    valve = element("valve", "V1", valveType="prv", status="active", setpoint=1.0e8)
    project = line(valve, fluid=custom_fluid(rho, 1.0e-3))
    network = built(project)
    data = network.valves["V1"]
    states: list[LinkState] = [NORMAL] * len(network.network.links)
    states[data.link_index] = active_state(network, data)
    result = solve_gga(network.network, states, tolerance=1.0e-9, max_iterations=100)
    q0 = foot * area(0.1)
    assert (not result.converged, result.iterations) == (True, 0)
    [found] = result.nonfinite_laws
    assert (found.link, found.element_id, found.value) == (data.link_index, "V1", "held head")
    assert found.flow == pytest.approx(q0, rel=1e-15)
    assert found.coefficient is None
    assert result.message == (
        f"{DIVERGED}: not a finite number in the law of 'V1' (held head at a flow of {q0:.3g} m³/s)"
    )
    assert solve_project(project).converged
