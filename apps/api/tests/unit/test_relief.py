"""The pressure relief valve (docs/proposals/pressure-relief-valve.md §3, §4, §5, §7.6): fluids'
functions and API 520's identity, the band root and its slope against a 60-digit solve, the
continuity and margin at full lift, the default overpressure and its scope, decision 14's
refusals at their edges, the builder and the closed start, the opening on the static difference
and the free-level rule (status._level_changes), each flag at its bound, a closed-off and a
floating side, the results, the trace, the methods summary, scenarios, goal seek, the API, a
system curve and the design checks.

Expected values come from fluids' functions called directly, from closed forms written out here
(the law transcribed again below, its band cubic solved with 60-digit decimals, its forward form,
and the pipes' Darcy-Weisbach losses), and from the proposal's measured cases (§7.1, by its
prototypes), never from the relief code itself, which the tests of the law (ReliefLaw, band_root)
call only as the code under test. Every pipe, level, set pressure, valve size and fluid below is
a made-up test input.
"""

import math
import random
import sys
from decimal import Decimal, localcontext
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fluids.constants import g, psi
from fluids.safety_valve import API526_A, API520_A_l, API520_Kv, API520_round_size, API526_letters
from scipy.optimize import brentq

from opensolve_pipe.main import app
from opensolve_pipe.models.api import GoalSeekRequest
from opensolve_pipe.models.goal_seek import Goal
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import Flag, SolvedState
from opensolve_pipe.services import goal_seek as gs
from opensolve_pipe.services.fluids import fluid_properties
from opensolve_pipe.services.scenarios import (
    ScenarioOverrideError,
    apply_scenario,
    solve_case,
    value_text,
)
from opensolve_pipe.services.solver import solve_project, system_curve
from opensolve_pipe.services.solver.builder import build_network
from opensolve_pipe.services.solver.elements import PipeSegment, segment_state
from opensolve_pipe.services.solver.errors import TopologyError
from opensolve_pipe.services.solver.methods import RELIEF_ASSUMPTION, methods_summary
from opensolve_pipe.services.solver.network import LinkKind
from opensolve_pipe.services.solver.relief import (
    CONSTANT_EXCESS,
    EXACT_CONSTANT,
    ReliefLaw,
    band_root,
    covering_letter,
    default_overpressure,
    kv_api520,
)
from opensolve_pipe.services.solver.status import Status, initial_controls

from .helpers import connection, custom_fluid, make_project, project_dict, reservoir, tee

RHO, MU = 998.0, 1.0e-3
"""Liquid A of the proposal's cases (the helpers' default custom fluid)."""
EPS = 4.5e-5
D_IN, D_OUT = 0.0525, 0.0779
"""m: the inlet and outlet pipes' bores of the proposal's network M (test inputs)."""
LETTER_F = {"kind": "api526", "letter": "F"}
A_F = API526_A[API526_letters.index("F")]
"""m²: API 526's effective area of F (fluids)."""
KD = 0.65
"""API 520's effective coefficient of discharge (fluids' API520_A_l default Kd)."""
ASME_SCOPE = 15.0 * psi
"""Pa: ASME VIII's scope, 15 psi (Pentair TP-V300 p. 5.3), with fluids' psi."""
THREE_PSI = 3.0 * psi
_clients = iter(range(1, 250))


def _client() -> TestClient:
    """A client of its own address, so the API's per-client limits never meet another test's."""
    return TestClient(app, client=(f"198.51.107.{next(_clients)}", 50000))


def _flags(state: SolvedState, code: str, element: str | None = "RV1") -> list[Flag]:
    return [
        f for f in state.flags if f.code == code and (element is None or f.component_id == element)
    ]


def _area(d: float) -> float:
    return math.pi * d * d / 4.0


# --------------------------------------------------------------------------- the law, again


def band_u(set_pressure: float, rq: float) -> Decimal:
    """√Δp in the band, 60 digits: the largest root of u³ − Δp_s u − RQ = 0 by Newton's method
    from √Δp_s + ∛(RQ), where the cubic is positive and convex, so the iterates fall to it."""
    with localcontext() as ctx:
        ctx.prec = 60
        a, b = Decimal(set_pressure), Decimal(rq)
        u = a.sqrt() + (b ** (Decimal(1) / 3) if b > 0 else Decimal(0))
        for _ in range(500):
            step = (u * u * u - a * u - b) / (3 * u * u - a)
            u -= step
            if abs(step) <= u * Decimal("1e-58"):
                break
        return u


def law_terms(
    c: float, set_pressure: float, op: float, q: float, rho: float = RHO
) -> tuple[float, float]:
    """(Δp − Δp_s, dΔp/dQ) of the law (proposal §1.1), from the cubic solved in decimals in the
    band and API 520's full-lift equation beyond Q_f = C √(2 Δp_s (1 + op)/ρ)."""
    with localcontext() as ctx:
        ctx.prec = 60
        cc, a, o, qq, r = (Decimal(x) for x in (c, set_pressure, op, q, rho))
        q_full = cc * (2 * a * (1 + o) / r).sqrt()
        if qq >= q_full:
            return float(r * qq * qq / (2 * cc * cc) - a), float(r * qq / (cc * cc))
        big_r = o * a / (cc * (2 / r).sqrt())
        u = band_u(set_pressure, float(big_r * qq)) if qq > 0 else a.sqrt()
        return float(big_r * qq / u), float(2 * u * big_r / (3 * u * u - a))


def law_head(c: float, set_pressure: float, op: float, q: float, dz: float = 0.0) -> float:
    """h(Q) = Δp_s/(ρ g) + dz + (Δp − Δp_s)/(ρ g), Q ≥ 0."""
    return set_pressure / (RHO * g) + dz + law_terms(c, set_pressure, op, q)[0] / (RHO * g)


def law_flow(c: float, set_pressure: float, op: float, difference: float) -> float:
    """The forward law (proposal §1.1) in decimals: Q = x C √(2 Δp/ρ), x = clip((Δp −
    Δp_s)/(op Δp_s), 0, 1)."""
    with localcontext() as ctx:
        ctx.prec = 60
        cc, a, o, dp, r = (Decimal(x) for x in (c, set_pressure, op, difference, RHO))
        x = min(Decimal(1), max(Decimal(0), (dp - a) / (o * a)))
        return float(x * cc * (2 * dp / r).sqrt()) if dp > 0 else 0.0


def pipe_loss(q: float, d: float, length: float, rho: float = RHO, mu: float = MU) -> float:
    return segment_state(
        PipeSegment(length, d, EPS, _area(d), mu / rho, g), q, "colebrook"
    ).head_loss


# --------------------------------------------------------------------------- projects


def relief(
    cid: str = "RV1",
    set_pressure: float = 5.0e5,
    capacity: dict[str, Any] | None = None,
    *,
    status: str | None = None,
    inlet: float | None = None,
    outlet: float | None = None,
) -> dict[str, Any]:
    ports: list[dict[str, Any]] = [
        {"id": "inlet", "nominalSize": 0.05},
        {"id": "outlet", "nominalSize": 0.05},
    ]
    if inlet is not None:
        ports[0]["elevation"] = inlet
    if outlet is not None:
        ports[1]["elevation"] = outlet
    data: dict[str, Any] = {
        "type": "relief_valve",
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "ports": ports,
        "setPressure": set_pressure,
        "capacity": capacity or LETTER_F,
    }
    if status is not None:
        data["status"] = status
    return data


def gate(cid: str, status: str = "isolated") -> dict[str, Any]:
    return {
        "type": "valve",
        "valveType": "gate",
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "status": status,
        "ports": [{"id": "inlet", "nominalSize": 0.1}, {"id": "outlet", "nominalSize": 0.1}],
    }


def pump(cid: str = "PU") -> dict[str, Any]:
    return {
        "type": "pump",
        "id": cid,
        "name": cid,
        "elevation": 0.0,
        "curveId": "C1",
        "ports": [{"id": "suction", "nominalSize": 0.1}, {"id": "discharge", "nominalSize": 0.1}],
    }


CURVE = {
    "id": "C1",
    "name": "test pump",
    "points": [
        {"flow": q, "head": h} for q, h in ((0.0, 40.0), (0.01, 37.0), (0.02, 30.0), (0.03, 18.0))
    ],
}
"""A test pump's curve: shutoff 40 m."""


def series_dict(
    p_r: float, element: dict[str, Any] | None = None, *, fluid: dict[str, Any] | None = None
) -> dict[str, Any]:
    """R1 (level 1 m, surface p_R) → 52.5 mm × 2 m → RV1 → 77.9 mm × 3 m → R3 (level 1 m)."""
    comps = [
        reservoir("R1", level=1.0, surface_pressure=p_r),
        element or relief(),
        reservoir("R3", level=1.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("RV1", "inlet"), length=2.0, diameter=D_IN),
        connection("L2", ("RV1", "outlet"), ("R3", "port_1"), length=3.0, diameter=D_OUT),
    ]
    return project_dict(comps, conns, fluid=fluid)


def series(p_r: float, element: dict[str, Any] | None = None, **kw: Any) -> Project:
    return Project.model_validate(series_dict(p_r, element, **kw))


def series_pressure(q: float, c: float, set_pressure: float, op: float, **fluid: float) -> float:
    """p_R that drives Q through the series network: ρ g (h_L1 + h(Q) + h_L2) (no entrance or
    exit loss without those fittings, D10; equal levels)."""
    rho, mu = fluid.get("rho", RHO), fluid.get("mu", MU)
    terms = law_terms(c, set_pressure, op, q, rho)[0] / (rho * g) + set_pressure / (rho * g)
    lines = pipe_loss(q, D_IN, 2.0, rho, mu) + pipe_loss(q, D_OUT, 3.0, rho, mu)
    return rho * g * (lines + terms)


def network_m(p_r: float, element: dict[str, Any] | None = None) -> Project:
    """The proposal's network M (§7.1): R1 (level 2 m, surface p_R) → 102.3 mm × 100 m → ideal
    tee T1 → 102.3 mm × 100 m → R2 (level 2 m); T1's branch → 52.5 mm × 2 m → RV1 (set 500 kPa,
    API 526 F) → 77.9 mm × 3 m → R3 (level 0)."""
    comps = [
        reservoir("R1", level=2.0, surface_pressure=p_r),
        tee("T1"),
        reservoir("R2", level=2.0),
        reservoir("R3", level=0.0),
        element or relief(),
    ]
    conns = [
        connection("M1", ("R1", "port_1"), ("T1", "run_inlet"), diameter=0.1023),
        connection("M2", ("T1", "run_outlet"), ("R2", "port_1"), diameter=0.1023),
        connection("B1", ("T1", "branch"), ("RV1", "inlet"), length=2.0, diameter=D_IN),
        connection("B2", ("RV1", "outlet"), ("R3", "port_1"), length=3.0, diameter=D_OUT),
    ]
    return make_project(comps, conns)


def deadhead(set_pressure: float, status: str | None = None) -> Project:
    """R1 (level 2 m) → PU (shutoff 40 m) → T1; T1's run → isolated gate → R2 (level 10 m); T1's
    branch → RV1 (API 526 L) → back to R1: with the gate shut the pump feeds only the relief
    valve, whose difference at zero flow is the shutoff head, ρ g × 40 m."""
    comps = [
        reservoir("R1", level=2.0, ports=("port_1", "port_2")),
        pump(),
        tee("T1"),
        gate("G1"),
        reservoir("R2", level=10.0),
        relief(
            set_pressure=set_pressure, capacity={"kind": "api526", "letter": "L"}, status=status
        ),
    ]
    conns = [
        connection("S", ("R1", "port_1"), ("PU", "suction"), length=5.0, diameter=0.1541),
        connection("D", ("PU", "discharge"), ("T1", "run_inlet"), length=5.0, diameter=0.1023),
        connection("P1", ("T1", "run_outlet"), ("G1", "inlet"), length=50.0, diameter=0.1023),
        connection("P2", ("G1", "outlet"), ("R2", "port_1"), length=50.0, diameter=0.1023),
        connection("B1", ("T1", "branch"), ("RV1", "inlet"), length=3.0, diameter=0.0779),
        connection("B2", ("RV1", "outlet"), ("R1", "port_2"), length=6.0, diameter=0.1023),
    ]
    return make_project(comps, conns, pump_library=[CURVE])


def _built(project: Project) -> Any:
    return build_network(project, fluid_properties(project.fluid))


# --------------------------------------------------------------------------- fluids and API 520


def test_fluids_docstring_examples() -> None:
    """§7.6: the fluids 1.3.1 functions the design rests on reproduce their docstrings, and the
    law's exact SI form gives API 520's Example 5 area within the rounding of its 11.78."""
    q = 6814 * 1.6666666666666667e-05
    rho = 0.9 * 999
    p1 = 1.1 * 1724e3 + 101325.0
    p2 = 0.2 * 1724e3 + 101325.0
    a0 = API520_A_l(
        m=rho * q, rho=rho, P1=p1, P2=p2, overpressure=0.1, Kd=0.65, Kw=0.97, Kc=1.0, Kv=1.0
    )
    assert a0 == pytest.approx(0.0030661356203, rel=1e-10)
    # The law at full lift on a 1 m² orifice, then the area that passes Q: Q is linear in A.
    unit = ReliefLaw(rho, g, KD * 1.0, (p1 - p2) / 1.1, 0.1, 0.0)
    exact = q / unit.q_full / 0.97  # Kw = 0.97 divides the area API 520 needs
    assert exact * (1.0 + CONSTANT_EXCESS) == pytest.approx(a0, rel=1e-12)
    assert API520_Kv(4525, edition="10E") == pytest.approx(0.9817287137013179, rel=1e-14)
    assert kv_api520(4525.0) == pytest.approx(0.9817287137013179, rel=1e-14)
    assert API520_round_size(1e-4) == pytest.approx(0.00012645136, rel=1e-12)
    assert covering_letter(1e-4) == "E"


def test_the_full_lift_law_is_api_520s_liquid_equation_for_every_letter() -> None:
    """Decision 4, §3.1 (S1f): API520_A_l at the law's full-lift flow and difference gives each
    letter's area × (1 + 6.092144×10⁻⁵), the rounding of API's 11.78 against the exact
    11.779282389196."""
    assert pytest.approx(11.779282389196, rel=1e-12) == EXACT_CONSTANT
    assert pytest.approx(6.092144e-5, rel=1e-6) == CONSTANT_EXCESS
    for letter, area in zip(API526_letters, API526_A, strict=True):
        law = ReliefLaw(RHO, g, KD * area, 5.0e5, 0.1, 0.0)
        sized = API520_A_l(
            m=RHO * law.q_full,
            rho=RHO,
            P1=101325.0 + law.full_lift_pressure,
            P2=101325.0,
            overpressure=0.1,
            Kd=KD,
            Kw=1.0,
            Kc=1.0,
            Kv=1.0,
        )
        assert sized / area == pytest.approx(1.0 + CONSTANT_EXCESS, rel=1e-13), letter


def test_the_covering_letter_is_the_smallest_api_526_letter_at_least_the_area() -> None:
    """Decision 7: fluids' API520_round_size; a letter's own area gives that letter, the next
    double above it the next letter, an area below D's gives D, one above T's none."""
    for i, (letter, area) in enumerate(zip(API526_letters, API526_A, strict=True)):
        assert covering_letter(area) == letter
        above = math.nextafter(area, math.inf)
        assert covering_letter(above) == (
            API526_letters[i + 1] if i + 1 < len(API526_letters) else None
        )
    assert covering_letter(1.0e-9) == "D"
    assert covering_letter(1.0) is None


# --------------------------------------------------------------------------- band root and slope


def _draw(rng: random.Random, op_range: tuple[float, float]) -> tuple[float, float, float, float]:
    rho = rng.uniform(700.0, 1300.0)
    c = math.exp(rng.uniform(math.log(1e-6), math.log(0.03)))
    dps = math.exp(rng.uniform(math.log(1e4), math.log(3e7)))
    op = math.exp(rng.uniform(math.log(op_range[0]), math.log(op_range[1])))
    return rho, c, dps, op


@pytest.mark.parametrize(
    ("op_range", "branch"), [((1e-3, 1.0 / 3.0), "trigonometric"), ((0.34, 1.0), "Cardano")]
)
def test_the_band_root_and_slope_match_a_60_digit_solve(
    op_range: tuple[float, float], branch: str
) -> None:
    """§3.1 (S1b), decision 13: Δp − Δp_s = RQ/u and dΔp/dQ = 2uR/(3u² − Δp_s) against the cubic
    solved to 60 digits, over the band, by both forms of the root (the trigonometric while
    27(RQ)² ≤ 4Δp_s³, which covers the band for op ≤ 1/3, Cardano's otherwise)."""
    rng = random.Random(f"relief band {branch}")
    worst = 0.0
    cardano = 0
    for _ in range(400):
        rho, c, dps, op = _draw(rng, op_range)
        law = ReliefLaw(rho, g, c, dps, op, 0.0)
        q = law.q_full * rng.uniform(1e-6, 1.0 - 1e-9)
        increment, slope = law.increment(q)
        expected = law_terms(c, dps, op, q, rho)
        worst = max(
            worst,
            abs(increment / expected[0] - 1.0),
            abs(slope / expected[1] - 1.0),
        )
        rq = law.band_coefficient * q
        cardano += 27.0 * rq * rq > 4.0 * dps**3
    assert worst < 1e-13
    assert (cardano == 0) is (branch == "trigonometric")


def test_the_slope_is_the_derivative_of_the_law() -> None:
    """dh/dQ against central differences of h, in the band and at full lift."""
    law = ReliefLaw(RHO, g, KD * A_F, 5.0e5, 0.1, 0.25)
    for q in (law.q_full * f for f in (0.05, 0.3, 0.7, 0.99, 1.2, 2.0)):
        step = q * 1e-6
        numeric = (law.head(q + step) - law.head(q - step)) / (2 * step)
        assert law.evaluate(q)[1] == pytest.approx(numeric, rel=1e-6)


def test_the_law_is_continuous_at_full_lift_where_its_slope_steps_up() -> None:
    """§3.1 (S1c, S1d): h is continuous at Q_f; the band's slope there, × C²/(ρ Q_f), is
    op/(2 + 3op), the least over the band, and the full-lift slope's is 1."""
    for op in (0.001, 0.1, 0.25, 1.0):
        c = KD * A_F
        law = ReliefLaw(RHO, g, c, 5.0e5, op, 0.0)
        below = math.nextafter(law.q_full, 0.0)
        assert law.head(below) == pytest.approx(law.head(law.q_full), rel=1e-13)
        assert law.pressure_difference(law.q_full) == pytest.approx(
            law.full_lift_pressure, rel=1e-15
        )
        scale = c * c / (RHO * law.q_full)
        margin = op / (2.0 + 3.0 * op)
        assert law.increment(below)[1] * scale == pytest.approx(margin, rel=1e-9)
        assert law.increment(law.q_full)[1] * scale == pytest.approx(1.0, rel=1e-15)
        for f in (0.01, 0.2, 0.5, 0.8, 0.95):
            q = law.q_full * f
            assert law.increment(q)[1] * c * c / (RHO * q) > margin


def test_zero_and_reverse_flow() -> None:
    """Decision 12: h(0) = h_set, holding z_in − z_out, with the finite positive slope
    R/(√Δp_s ρ g); Newton sees the odd extension about h_set for Q < 0."""
    law = ReliefLaw(RHO, g, KD * A_F, 5.0e5, 0.1, -0.5)
    assert law.h_set == pytest.approx(5.0e5 / (RHO * g) - 0.5, rel=1e-15)
    head, slope = law.evaluate(0.0)
    assert head == law.h_set
    r = 0.1 * 5.0e5 / (KD * A_F * math.sqrt(2.0 / RHO))
    assert slope == pytest.approx(r / (math.sqrt(5.0e5) * RHO * g), rel=1e-14)
    q = 0.4 * law.q_full
    assert law.evaluate(-q)[0] == pytest.approx(2.0 * law.h_set - law.head(q), rel=1e-15)
    assert law.evaluate(-q)[1] == law.evaluate(q)[1]
    assert law.lift(-q) == 0.0
    assert law.state(-q) == "closed"
    assert law.lift(q) == pytest.approx(
        q / (KD * A_F * math.sqrt(2.0 * law.pressure_difference(q) / RHO)), rel=1e-15
    )


# --------------------------------------------------------------------------- default and refusals


def test_the_default_overpressure_is_asmes_10_percent_or_3_psi() -> None:
    """Decision 6: max(10 %, 3 psi/Δp_s); 0.1 from the 3 psi crossover (30 psi) on, 0.2 at
    ASME VIII's 15 psi scope."""
    crossover = 30.0 * psi
    assert crossover == pytest.approx(206842.72, abs=0.01)
    assert default_overpressure(crossover) == pytest.approx(0.1, rel=1e-15)
    assert default_overpressure(2.0 * crossover) == 0.1
    below = crossover * (1.0 - 1e-6)
    assert default_overpressure(below) == pytest.approx(THREE_PSI / below, rel=1e-15)
    assert default_overpressure(below) > 0.1
    assert default_overpressure(ASME_SCOPE) == pytest.approx(0.2, rel=1e-15)


@pytest.mark.parametrize(
    "capacity",
    [
        LETTER_F,
        {"kind": "effective", "area": 2.0e-4},
        {"kind": "certified", "area": 2.0e-4, "dischargeCoefficient": 0.7},
    ],
    ids=["letter", "effective", "certified without overpressure"],
)
def test_a_default_overpressure_below_asmes_scope_is_refused(capacity: dict[str, Any]) -> None:
    """Decision 14, §3.7: a set just below 15 psi with ASME's default overpressure is refused
    (422, quoting the set and the bound, with the remedy); at 15 psi it builds."""
    _built(series(4.0e5, relief(set_pressure=ASME_SCOPE, capacity=capacity)))
    below = math.nextafter(ASME_SCOPE, 0.0)
    with pytest.raises(TopologyError) as caught:
        _built(series(4.0e5, relief(set_pressure=below, capacity=capacity)))
    [issue] = caught.value.issues
    assert (issue.code, issue.component_ids) == ("RELIEF_VALVE_OUT_OF_RANGE", ["RV1"])
    assert f"its set pressure of {below:.6g} Pa is below ASME VIII's scope" in issue.message
    assert "15 psi (103421 Pa)" in issue.message
    remedy = (
        "enter its certified overpressure at full lift"
        if capacity["kind"] == "certified"
        else "enter the valve's certified capacity"
    )
    assert remedy in issue.message


def test_a_certified_overpressure_needs_no_scope() -> None:
    """Decision 6: a certified valve with its own overpressure is cited below 15 psi too."""
    capacity = {
        "kind": "certified",
        "area": 2.0e-4,
        "dischargeCoefficient": 0.7,
        "overpressure": 0.25,
    }
    built = _built(series(1.0e5, relief(set_pressure=5.0e4, capacity=capacity)))
    law = built.valves["RV1"].relief.law
    assert (law.set_pressure, law.overpressure) == (5.0e4, 0.25)


def test_a_law_the_floating_point_cannot_represent_is_refused_after_orifice_issues() -> None:
    """Decision 14: C = Kd·A subnormal is refused, quoting C, the set and the overpressure,
    listed after ORIFICE_OUT_OF_RANGE (here a bore at the pipe's)."""
    tiny = {"kind": "effective", "area": 1.0e-310}
    data = series_dict(4.0e5, relief(capacity=tiny))
    data["components"] += [
        reservoir("R4", level=2.0),
        {
            "type": "orifice",
            "id": "O1",
            "name": "O1",
            "elevation": 0.0,
            "ports": [{"id": "inlet", "nominalSize": 0.1}, {"id": "outlet", "nominalSize": 0.1}],
            "boreDiameter": 0.2,
        },
        reservoir("R5", level=1.0),
    ]
    data["connections"] += [
        connection("L3", ("R4", "port_1"), ("O1", "inlet")),
        connection("L4", ("O1", "outlet"), ("R5", "port_1")),
    ]
    project = Project.model_validate(data)
    with pytest.raises(TopologyError) as caught:
        _built(project)
    codes = [i.code for i in caught.value.issues]
    assert codes[-2:] == ["ORIFICE_OUT_OF_RANGE", "RELIEF_VALVE_OUT_OF_RANGE"]
    message = caught.value.issues[-1].message
    assert "C = Kd·A = 6.5e-311 m²" in message
    assert "not a finite positive normal floating-point number" in message


def _certified(area: float, k: float = 1.0, op: float = 0.1) -> dict[str, Any]:
    """A certified capacity with its own overpressure (decision 14's scope never applies)."""
    return {"kind": "certified", "area": area, "dischargeCoefficient": k, "overpressure": op}


def _refusal(project: Project) -> str:
    with pytest.raises(TopologyError) as caught:
        _built(project)
    [issue] = caught.value.issues
    assert (issue.code, issue.component_ids) == ("RELIEF_VALVE_OUT_OF_RANGE", ["RV1"])
    return issue.message


def _least(holds: Any, estimate: float) -> float:
    """The least double at which ``holds`` (true from some double on) is true, within a few
    hundred units in the last place of ``estimate``."""
    x = estimate
    for _ in range(400):
        if holds(x):
            break
        x = math.nextafter(x, math.inf)
    for _ in range(400):
        if not holds(math.nextafter(x, 0.0)):
            break
        x = math.nextafter(x, 0.0)
    assert holds(x)
    assert not holds(math.nextafter(x, 0.0))
    return x


def test_a_c_whose_square_underflows_is_refused_not_a_server_error() -> None:
    """Decision 14: the law at full lift divides by C², so a C whose square is not a normal
    double is refused, though C, Q_f and R are normal. A certified area of 1e-200 m² (inside the
    schema's bounds) was a ZeroDivisionError in the solve: HTTP 500 from /solve and from a goal
    seek whose bound reached it; now 422 and a bounds 400 located by index."""
    data = series_dict(7.5e5, relief(capacity=_certified(1e-200, 0.9)))
    response = _client().post("/api/v1/solve", json={"project": data})
    assert response.status_code == 422, response.text
    [issue] = response.json()["issues"]
    assert (issue["code"], issue["componentIds"]) == ("RELIEF_VALVE_OUT_OF_RANGE", ["RV1"])
    assert "C = Kd·A = 9e-201 m²" in issue["message"]
    assert "gives C² = 0 m⁴, which the law at full lift divides by" in issue["message"]
    assert issue["message"].endswith("enter a larger area or coefficient of discharge")
    variables = [{"field": "capacity.area", "lower": 1e-200, "upper": 1e-2}]
    goals = [{"quantity": "port_pressure", "elementId": "RV1", "portId": "inlet", "target": 4e5}]
    base = series_dict(4.4e5, relief(set_pressure=3.5e5, capacity=_certified(1e-3, 0.9)))
    with pytest.raises(gs.GoalSeekInputError) as caught:
        _goal_seek(base, variables, goals)
    [bound] = caught.value.issues
    assert bound.code == "RELIEF_VALVE_OUT_OF_RANGE"
    assert bound.message.startswith(
        "body.variables.0.lower: the relief valve's law is not representable in floating point "
        "at this orifice area (Kd·A, its square,"
    )
    assert "RV1" not in bound.message
    assert "e-200" not in bound.message
    body = {
        "project": base,
        "variables": [{"kind": "component", "componentId": "RV1", **variables[0]}],
        "goals": goals,
    }
    assert _client().post("/api/v1/goal-seek", json=body).status_code == 400


def test_the_representability_refusal_at_its_edges() -> None:
    """§7.6: each representability bound at its edge, with K = 1 so that C is the area: C² at
    the least normal double (accepted) and one step below (refused); the band root's scale
    2 Δp_s √(Δp_s/3) likewise in the set (a certified valve takes any set); and R, which a tiny
    overpressure on the largest valve takes below the least normal double."""
    edge = _least(lambda c: c * c >= sys.float_info.min, math.sqrt(sys.float_info.min))
    _built(series(7.5e5, relief(capacity=_certified(edge))))
    below = math.nextafter(edge, 0.0)
    message = _refusal(series(7.5e5, relief(capacity=_certified(below))))
    assert f"C = Kd·A = {below:.6g} m²" in message
    assert f"gives C² = {below * below:.6g} m⁴" in message

    def scale(set_pressure: float) -> float:
        return set_pressure * (2.0 * math.sqrt(set_pressure / 3.0))

    # 2 x √(x/3) = (2/√3) x^1.5 reaches the least normal double at x = (min √3/2)^(2/3)
    low = _least(
        lambda x: scale(x) >= sys.float_info.min,
        (sys.float_info.min * math.sqrt(3.0) / 2.0) ** (2.0 / 3.0),
    )
    capacity = _certified(1e-4, 0.9, 1.0)
    _built(series(1.0, relief(set_pressure=low, capacity=capacity)))
    below = math.nextafter(low, 0.0)
    message = _refusal(series(1.0, relief(set_pressure=below, capacity=capacity)))
    assert f"with a set pressure of {below:.6g} Pa" in message
    assert "gives the band root's scale 2 Δp_s √(Δp_s/3) = " in message
    assert message.endswith("enter a larger set pressure")
    # R = op Δp_s/(C √(2/ρ)) at the largest area, K 1: subnormal at op 1e-305 on a 1 mPa set
    big = math.pi * 10.0**2 / 4.0
    tiny = _certified(big, 1.0, 1e-305)
    message = _refusal(series(1.0, relief(set_pressure=1e-3, capacity=tiny)))
    r = 1e-305 * 1e-3 / (big * math.sqrt(2.0 / RHO))
    assert 0.0 < r < sys.float_info.min
    assert f"the band coefficient R = {r:.6g} that is not a finite positive normal" in message


def test_a_c_that_underflows_to_zero_quotes_q_f_as_zero() -> None:
    """Decision 14's text quotes the values the law would use: with Kd·A = 0 (an area and a
    coefficient whose product underflows) Q_f = C √(2 Δp_f/ρ) is 0 and R, dividing by C, is
    infinite; Q_f was quoted as inf."""
    message = _refusal(series(7.5e5, relief(capacity=_certified(1e-200, 1e-200))))
    assert "C = Kd·A = 0 m²" in message
    assert "the full-lift flow Q_f = 0 m³/s or the band coefficient R = inf" in message


def test_the_band_root_where_its_two_branch_tests_round_differently() -> None:
    """Next to 27 (RQ)² = 4 Δp_s³ the trigonometric test can fail while Cardano's radicand
    rounds below zero: at this pair (found by stepping a few units in the last place about the
    boundary) the root raised a math domain error; it is the 60-digit root."""
    a, rq = 42101985.83804243, 105148234451.42006
    assert 27.0 * rq * rq > 4.0 * a * a * a
    assert rq * rq / 4.0 - a * a * a / 27.0 < 0.0
    assert band_root(a, rq) == pytest.approx(float(band_u(a, rq)), rel=1e-14)


# --------------------------------------------------------------------------- builder and status


def test_the_builder_adds_a_valve_link_with_the_set_head_as_its_cracking_head() -> None:
    """§3.8, decisions 5 and 10: a LinkKind.VALVE link inlet → outlet in built.valves, the
    cracking head h_set = Δp_s/(ρ g) + z_in − z_out (0 when locked closed), and the full-lift K
    on the inlet bore, (A_in/C)², for the trace only."""
    built = _built(series(4.0e5, relief(inlet=1.0, outlet=1.5)))
    data = built.valves["RV1"]
    link = built.network.links[data.link_index]
    assert link.kind is LinkKind.VALVE
    net = built.network
    assert (net.nodes[link.start].key, net.nodes[link.end].key) == ("RV1:inlet", "RV1:outlet")
    assert data.cracking_head == pytest.approx(5.0e5 / (RHO * g) - 0.5, rel=1e-15)
    assert data.relief is not None
    assert data.relief.law.dz == -0.5
    assert data.resistance.k == pytest.approx((_area(D_IN) / (KD * A_F)) ** 2, rel=1e-15)
    locked = _built(series(4.0e5, relief(status="locked_closed")))
    assert locked.valves["RV1"].cracking_head == 0.0


def test_a_relief_valve_starts_closed_and_is_fixed_only_when_locked_closed() -> None:
    """Decision 11: in a solve its normal state, CLOSED, whether active or locked closed. A
    system-curve point (forced flows) starts an active one open, as a check valve (§3.5)."""
    for status, fixed in ((None, False), ("locked_closed", True)):
        built = _built(series(4.0e5, relief(status=status)))
        control = initial_controls(built)["RV1"]
        assert (control.kind, control.status, control.fixed) == ("relief", Status.CLOSED, fixed)
        forced = initial_controls(built, {})["RV1"]
        assert forced.status is (Status.CLOSED if fixed else Status.OPEN)
        assert forced.fixed is fixed


def test_a_pump_deadheaded_behind_a_valve_set_above_its_shutoff_runs_at_zero_flow() -> None:
    """Decision 11 (C7): started closed, the pump runs at zero flow and the valve's inlet reads
    the shutoff pressure, ρ g (2 m + 40 m); locked closed the same, though set below it; active
    and set below the shutoff it relieves."""
    for set_pressure, status in ((4.5e5, None), (3.0e5, "locked_closed")):
        state = solve_project(deadhead(set_pressure, status))
        assert state.converged
        r = state.relief_valve_results["RV1"]
        assert (r.state, r.flow, r.lift) == ("closed", 0.0, 0.0)
        assert state.pump_results["PU"].operating_flow == 0.0
        assert r.inlet_pressure == pytest.approx(RHO * g * 42.0, rel=1e-12)
        assert r.back_pressure == pytest.approx(RHO * g * 2.0, rel=1e-12)
        assert r.set_ratio == pytest.approx(RHO * g * 40.0 / set_pressure, rel=1e-12)
        assert _flags(state, "RELIEF_VALVE_OPEN") == []
        assert _flags(state, "CORRELATION_OUT_OF_RANGE") == []
        assert _flags(state, "RELIEF_VALVE_CLOSED") == []
    relieving = solve_project(deadhead(3.0e5))
    assert relieving.relief_valve_results["RV1"].state != "closed"
    assert relieving.relief_valve_results["RV1"].flow > 0.0


# --------------------------------------------------------------------------- solved states


def test_network_m_reproduces_the_proposals_cases_c1_to_c3() -> None:
    """§7.1 C1-C3 (measured by the proposal's prototypes and an independent review): closed,
    partial lift and full lift."""
    c1 = solve_project(network_m(6.0e5))
    r1 = c1.relief_valve_results["RV1"]
    assert (r1.state, r1.flow) == ("closed", 0.0)
    assert r1.inlet_pressure == pytest.approx(319574.0734, rel=1e-9)
    c2 = solve_project(network_m(1.05e6)).relief_valve_results["RV1"]
    assert c2.state == "partial_lift"
    assert c2.flow == pytest.approx(0.002221210802348, rel=1e-9)
    assert c2.lift == pytest.approx(0.5311270926, rel=1e-9)
    assert c2.flow_ratio == pytest.approx(0.5196842317, rel=1e-9)
    assert c2.inlet_pressure == pytest.approx(526131.6131, rel=1e-9)
    assert c2.back_pressure == pytest.approx(-7.754453834, rel=1e-7)
    assert c2.total_pressure_difference == pytest.approx(526556.3546, rel=1e-9)
    assert c2.pressure_drop == pytest.approx(526139.3676, rel=1e-9)
    assert c2.full_lift_flow == pytest.approx(0.004274154702, rel=1e-9)
    c3 = solve_project(network_m(1.4e6)).relief_valve_results["RV1"]
    assert c3.state == "full_lift"
    assert c3.flow == pytest.approx(0.004732647684257, rel=1e-9)
    assert c3.flow_ratio == pytest.approx(1.107271031, rel=1e-9)
    assert c3.inlet_pressure == pytest.approx(672346.5806, rel=1e-9)


def test_the_result_holds_the_static_drop_identity_and_the_ports_elevation_term() -> None:
    """§2.2 (C4's geometry): Δp_t = ρ g (h − (z_in − z_out)), the static drop Δp_t − ρ(v_in² −
    v_out²)/2, the lift from the flow, setRatio Δp_t/Δp_s, flowRatio Q/Q_f, Re on the orifice;
    the flow the closed form gives for these heads."""
    q = 0.0025
    c = KD * A_F
    p_r = series_pressure(q, c, 5.0e5, 0.1) + RHO * g * (-0.5)  # h_set holds z_in − z_out
    state = solve_project(series(p_r, relief(outlet=0.5)))
    r = state.relief_valve_results["RV1"]
    assert r.flow == pytest.approx(q, rel=1e-9)
    assert r.total_pressure_difference == pytest.approx(RHO * g * (r.head_loss + 0.5), rel=1e-12)
    v_in, v_out = r.flow / _area(D_IN), r.flow / _area(D_OUT)
    assert r.pressure_drop == pytest.approx(
        r.total_pressure_difference - RHO * (v_in**2 - v_out**2) / 2.0, rel=1e-12
    )
    assert r.inlet_pressure is not None
    assert r.back_pressure is not None
    assert r.pressure_drop == pytest.approx(r.inlet_pressure - r.back_pressure, rel=1e-12)
    assert r.set_ratio == pytest.approx(r.total_pressure_difference / 5.0e5, rel=1e-15)
    assert r.flow_ratio == pytest.approx(r.flow / r.full_lift_flow, rel=1e-15)
    assert r.lift == pytest.approx(
        r.flow / (c * math.sqrt(2.0 * r.total_pressure_difference / RHO)), rel=1e-9
    )
    re = RHO * (r.flow / A_F) * math.sqrt(4.0 * A_F / math.pi) / MU
    assert r.reynolds_number == pytest.approx(re, rel=1e-14)
    assert (r.set_pressure, r.overpressure, r.overpressure_source) == (5.0e5, 0.1, "asme_default")
    assert r.full_lift_pressure_difference == pytest.approx(5.5e5, rel=1e-15)
    assert r.capacity.kind == "api526"
    assert (r.capacity.letter, r.capacity.area, r.capacity.discharge_coefficient) == (
        "F",
        A_F,
        KD,
    )


@pytest.mark.parametrize("side", ["below", "above"])
def test_each_relieving_flag_at_full_lift(side: str) -> None:
    """Decision 15, §3.6: just below Q_f the partial-lift warning (the linear convention) and
    no RELIEF_VALVE_OPEN; just above it RELIEF_VALVE_OPEN, beyond its rated overpressure, and
    no partial-lift warning."""
    c = KD * A_F
    q_full = c * math.sqrt(2.0 * 5.5e5 / RHO)
    q = q_full * (1.0 - 1e-5 if side == "below" else 1.0 + 1e-5)
    state = solve_project(series(series_pressure(q, c, 5.0e5, 0.1)))
    r = state.relief_valve_results["RV1"]
    assert r.flow == pytest.approx(q, rel=1e-9)
    partial = [
        f for f in _flags(state, "CORRELATION_OUT_OF_RANGE") if f.details["limit"] == "partial_lift"
    ]
    opened = _flags(state, "RELIEF_VALVE_OPEN")
    if side == "below":
        assert r.state == "partial_lift"
        [flag] = partial
        assert opened == []
        assert flag.severity == "warning"
        assert flag.details["lift"] == pytest.approx(r.lift, rel=1e-15)
        assert flag.details["setRatio"] == pytest.approx(r.set_ratio, rel=1e-15)
        assert flag.details["overpressure"] == 0.1
        assert "relieves at partial lift" in flag.message
        assert "Pentair TP-V300 Fig. 4-12" in flag.message
    else:
        assert r.state == "full_lift"
        assert r.lift == 1.0
        [flag] = opened
        assert partial == []
        assert flag.severity == "info"
        assert flag.details["flowRatio"] == pytest.approx(1.0 + 1e-5, rel=1e-8)
        assert "beyond its rated overpressure" in flag.message


def test_no_relief_flag_on_a_closed_valve_with_a_result() -> None:
    """Decision 15: a closed valve with a result has its state, and no flag."""
    state = solve_project(series(4.0e5))
    r = state.relief_valve_results["RV1"]
    assert (r.state, r.flow, r.reynolds_number) == ("closed", 0.0, None)
    assert r.set_ratio == pytest.approx(4.0e5 / 5.0e5, rel=1e-12)
    for code in ("RELIEF_VALVE_OPEN", "RELIEF_VALVE_CLOSED", "CORRELATION_OUT_OF_RANGE"):
        assert _flags(state, code) == []


def test_a_closed_off_inlet_side_leaves_no_result_and_says_why() -> None:
    """Decisions 15-16: an isolated gate cuts the inlet off; RV1 has no result and
    RELIEF_VALVE_CLOSED names the side, the section and the levels that keep it closed. Locked
    closed, no flag."""
    comps = [reservoir("R1", level=1.0), gate("G1"), relief(), reservoir("R3", level=1.0)]
    conns = [
        connection("L0", ("R1", "port_1"), ("G1", "inlet"), length=2.0),
        connection("L1", ("G1", "outlet"), ("RV1", "inlet"), length=2.0, diameter=D_IN),
        connection("L2", ("RV1", "outlet"), ("R3", "port_1"), length=3.0, diameter=D_OUT),
    ]
    state = solve_project(make_project(comps, conns))
    assert state.converged
    assert "RV1" not in state.relief_valve_results
    [flag] = _flags(state, "RELIEF_VALVE_CLOSED")
    assert flag.severity == "info"
    assert (flag.details["side"], flag.details["section"]) == ("inlet", "closed_off")
    assert flag.details["setPressure"] == 5.0e5
    assert flag.details["pressureLimit"] == pytest.approx(RHO * g * 1.0 + 5.0e5, rel=1e-12)
    assert "the section on its inlet side is closed off" in flag.message
    comps[2] = relief(status="locked_closed")
    locked = solve_project(make_project(comps, conns))
    assert "RV1" not in locked.relief_valve_results
    assert _flags(locked, "RELIEF_VALVE_CLOSED") == []


def _closed_loop() -> Project:
    """C16's shape: a pump loop whose only fixed head is the open discharge of RV1 (set 300
    kPa) at a reference node at 0 kPa(g)."""
    comps = [
        pump(),
        tee("T1"),
        relief(set_pressure=3.0e5),
        {
            "type": "reference_node",
            "referenceType": "ideal",
            "id": "N1",
            "name": "N1",
            "elevation": 0.0,
            "pressure": 0.0,
            "ports": [{"id": "port_1", "nominalSize": 0.08}],
        },
    ]
    conns = [
        connection("L1", ("PU", "discharge"), ("T1", "run_inlet"), length=150.0, diameter=0.1023),
        connection("L2", ("T1", "run_outlet"), ("PU", "suction"), length=150.0, diameter=0.1023),
        connection("B1", ("T1", "branch"), ("RV1", "inlet"), length=2.0, diameter=D_IN),
        connection("B2", ("RV1", "outlet"), ("N1", "port_1"), length=1.0, diameter=D_OUT),
    ]
    return make_project(comps, conns, pump_library=[CURVE])


def test_a_floating_inlet_side_leaves_no_result_and_names_the_levels() -> None:
    """C16 (§3.4): started closed, the loop floats (UNDETERMINED_PRESSURE) and circulates where
    the pump's head equals its friction; RV1 has no result, and RELIEF_VALVE_CLOSED names every
    inlet pressure up to its back pressure (0) plus its set as a level that keeps it closed."""
    state = solve_project(_closed_loop())
    assert state.converged
    q = state.link_results["L1"].flow
    assert q > 0.0
    assert state.pump_results["PU"].operating_head == pytest.approx(
        2.0 * pipe_loss(q, 0.1023, 150.0), rel=1e-9
    )
    assert "RV1" not in state.relief_valve_results
    assert _flags(state, "UNDETERMINED_PRESSURE", None)
    [flag] = _flags(state, "RELIEF_VALVE_CLOSED")
    assert (flag.details["side"], flag.details["section"]) == ("inlet", "floating")
    assert flag.details["pressureLimit"] == pytest.approx(3.0e5, abs=1e-6)
    assert "has no fixed pressure level (UNDETERMINED_PRESSURE)" in flag.message
    assert "every inlet static pressure up to 300000 Pa(g)" in flag.message


def test_the_closed_flag_claims_only_the_levels_that_keep_this_valve_closed() -> None:
    """Decision 15: between two closed relief valves in series (R1 at 900 kPa(g), each set at
    500 kPa) the middle section is closed off. RVb stays closed up to an inlet of 500 kPa(g)
    and RVa down to a back pressure of 400 kPa(g), so the section's steady states are 400-500
    kPa(g): each flag names its own valve's bound only, not each level as a steady state, and
    quotes the bound without the other side's pressure (here round-off of 0, 4e-15 Pa(g))."""
    comps = [
        reservoir("R1", level=0.0, surface_pressure=9.0e5),
        relief("RVa"),
        relief("RVb"),
        reservoir("R3", level=0.0),
    ]
    conns = [
        connection("L1", ("R1", "port_1"), ("RVa", "inlet"), length=2.0, diameter=D_IN),
        connection("L2", ("RVa", "outlet"), ("RVb", "inlet"), length=1.0, diameter=D_IN),
        connection("L3", ("RVb", "outlet"), ("R3", "port_1"), length=3.0, diameter=D_OUT),
    ]
    state = solve_project(make_project(comps, conns))
    assert state.converged
    assert state.relief_valve_results == {}
    [a] = _flags(state, "RELIEF_VALVE_CLOSED", "RVa")
    [b] = _flags(state, "RELIEF_VALVE_CLOSED", "RVb")
    assert (a.details["side"], b.details["side"]) == ("outlet", "inlet")
    assert a.details["pressureLimit"] == pytest.approx(4.0e5, rel=1e-12)
    assert b.details["pressureLimit"] == pytest.approx(5.0e5, rel=1e-12)
    for flag in (a, b):
        assert "is a steady state, that is" not in flag.message
        assert (
            "the valve stays closed at every level of that section at which the difference does "
            "not exceed its set pressure (500000 Pa)"
        ) in flag.message
        assert flag.message.endswith(
            "whether such a level is a steady state depends also on the other elements around "
            "that section"
        )
    assert "every back pressure down to 400000 Pa(g), its inlet pressure less its set" in a.message
    assert "every inlet static pressure up to 500000 Pa(g), its back pressure plus its set" in (
        b.message
    )
    assert "e-1" not in b.message


def test_a_valve_inside_a_floating_section_has_its_flow_and_no_pressures() -> None:
    """§2.2: a valve inside a floating section has its flow, lift and differences, and null
    pressures; no flashing check there."""
    comps = [
        pump(),
        tee("T1"),
        tee("T2"),
        tee("T3"),
        relief(
            set_pressure=1.5e5,
            capacity={
                "kind": "certified",
                "area": 2.0e-4,
                "dischargeCoefficient": 0.8,
                "overpressure": 0.1,
            },
        ),
        gate("G1"),
        reservoir("R1", level=2.0),
    ]
    conns = [
        connection("L1", ("PU", "discharge"), ("T1", "run_inlet"), length=5.0, diameter=0.1023),
        connection("L2", ("T1", "run_outlet"), ("T2", "run_inlet"), length=200.0, diameter=D_IN),
        connection("L3", ("T2", "run_outlet"), ("T3", "run_inlet"), length=5.0, diameter=0.1023),
        connection("L4", ("T3", "run_outlet"), ("PU", "suction"), length=5.0, diameter=0.1023),
        connection("B1", ("T1", "branch"), ("RV1", "inlet"), length=2.0, diameter=D_IN),
        connection("B2", ("RV1", "outlet"), ("T2", "branch"), length=2.0, diameter=D_OUT),
        connection("B3", ("T3", "branch"), ("G1", "inlet"), length=2.0, diameter=0.1023),
        connection("B4", ("G1", "outlet"), ("R1", "port_1"), length=2.0, diameter=0.1023),
    ]
    state = solve_project(make_project(comps, conns, pump_library=[CURVE]))
    assert state.converged
    r = state.relief_valve_results["RV1"]
    assert r.flow > 0.0
    assert (r.inlet_pressure, r.back_pressure) == (None, None)
    assert r.head_loss == pytest.approx(law_head(0.8 * 2.0e-4, 1.5e5, 0.1, r.flow), rel=1e-9)
    assert _flags(state, "BELOW_VAPOR_PRESSURE") == []


def test_a_flashing_outlet_and_a_viscous_liquid_are_flagged_while_relieving() -> None:
    """Decision 15: the outlet's absolute static pressure below the vapor pressure while it
    relieves (BELOW_VAPOR_PRESSURE on the component, backAbsolutePressure); μ ≥ 0.1 Pa·s
    (CORRELATION_OUT_OF_RANGE, viscosity) with API 520 10E's Kv at the solved flow."""
    c = KD * A_F
    hot = custom_fluid(vapor_pressure=1.5e5)
    flashing = solve_project(series(series_pressure(0.002, c, 5.0e5, 0.1), fluid=hot))
    r = flashing.relief_valve_results["RV1"]
    assert r.back_pressure is not None
    [flag] = [
        f for f in _flags(flashing, "BELOW_VAPOR_PRESSURE") if "backAbsolutePressure" in f.details
    ]
    assert flag.severity == "invalid"
    assert flag.details["backAbsolutePressure"] == pytest.approx(
        r.back_pressure + 101325.0, rel=1e-12
    )
    assert flag.details["vaporPressure"] == 1.5e5
    closed = solve_project(series(4.0e5, fluid=hot))
    assert not [
        f for f in _flags(closed, "BELOW_VAPOR_PRESSURE") if "backAbsolutePressure" in f.details
    ]

    viscous = custom_fluid(viscosity=0.2)
    q = 1.05 * c * math.sqrt(2.0 * 5.5e5 / RHO)
    state = solve_project(series(series_pressure(q, c, 5.0e5, 0.1, mu=0.2), fluid=viscous))
    r = state.relief_valve_results["RV1"]
    assert r.flow == pytest.approx(q, rel=1e-9)
    re = RHO * (r.flow / A_F) * math.sqrt(4.0 * A_F / math.pi) / 0.2
    [flag] = [
        f for f in _flags(state, "CORRELATION_OUT_OF_RANGE") if f.details["limit"] == "viscosity"
    ]
    assert flag.details["value"] == 0.2
    assert flag.details["lower"] == 0.1
    assert flag.details["kv"] == pytest.approx(API520_Kv(re, edition="10E"), rel=1e-12)
    assert "Kv is not applied" in flag.message
    thin = solve_project(series(series_pressure(q, c, 5.0e5, 0.1)))
    assert not [
        f for f in _flags(thin, "CORRELATION_OUT_OF_RANGE") if f.details["limit"] == "viscosity"
    ]


@pytest.mark.parametrize("mu", [0.1, math.nextafter(0.1, 0.0)], ids=["at 0.1", "just below"])
def test_the_viscosity_flag_at_its_bound(mu: float) -> None:
    """§7.6, decision 15: CORRELATION_OUT_OF_RANGE (viscosity) from μ = 0.1 Pa·s on, where API
    520 applies Kv (fluids' API520_Kv docstring), and not one double below it."""
    c = KD * A_F
    q = 1.05 * c * math.sqrt(2.0 * 5.5e5 / RHO)
    p_r = series_pressure(q, c, 5.0e5, 0.1, mu=mu)
    state = solve_project(series(p_r, fluid=custom_fluid(viscosity=mu)))
    assert state.relief_valve_results["RV1"].flow == pytest.approx(q, rel=1e-9)
    flagged = [
        f for f in _flags(state, "CORRELATION_OUT_OF_RANGE") if f.details["limit"] == "viscosity"
    ]
    if mu >= 0.1:
        [flag] = flagged
        assert (flag.details["value"], flag.details["lower"]) == (mu, 0.1)
    else:
        assert flagged == []


@pytest.mark.parametrize("outlet", [0.5, -0.5], ids=["outlet above", "outlet below"])
def test_the_valve_opens_on_the_static_difference_not_the_egl_difference(outlet: float) -> None:
    """Decision 10 (§1.3 item 15): h_set = Δp_s/(ρ g) + z_in − z_out, so the valve opens once the
    static pressure difference at zero flow exceeds its set, whatever its ports' elevations; a
    check valve's cracking head, without the elevation term, would read the EGL difference.
    Inside the window between the two readings, on the series network with equal reservoir
    levels (1 m) and the inlet port at 0: with the outlet port 0.5 m up and a static difference
    of 502 kPa at zero flow (the EGL difference ρ g × 0.5 m less, below the 500 kPa set) it
    opens and relieves the flow the closed form gives; with it 0.5 m down and 498 kPa (the EGL
    difference above the set) it stays closed."""
    rho_g = RHO * g
    c = KD * A_F
    # at zero flow p_in = p_R + ρ g × 1 m and p_out = ρ g (1 m − z_out): static = p_R + ρ g z_out
    static = 5.02e5 if outlet > 0.0 else 4.98e5
    p_r = static - rho_g * outlet
    egl_difference = p_r  # EGL_in − EGL_out at zero flow, × ρ g
    assert (egl_difference < 5.0e5) is (outlet > 0.0)
    state = solve_project(series(p_r, relief(outlet=outlet)))
    assert state.converged, state.convergence.message
    r = state.relief_valve_results["RV1"]
    if outlet > 0.0:
        # p_R = ρ g (h_L1 + h(Q) + h_L2) with h_set holding z_in − z_out = −0.5 m
        q = brentq(
            lambda x: series_pressure(x, c, 5.0e5, 0.1) - rho_g * outlet - p_r,
            1e-9,
            1e-2,
            xtol=1e-18,
            rtol=1e-15,
        )
        assert r.state == "partial_lift"
        assert r.flow == pytest.approx(q, rel=1e-9)
    else:
        assert (r.state, r.flow) == ("closed", 0.0)
        assert r.set_ratio == pytest.approx(static / 5.0e5, rel=1e-12)


def test_the_free_level_rule_takes_the_relief_valves_check_rule_at_its_set_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§3.4, decision 10 (status._level_changes): two PSVs in series in a pump loop whose only
    fixed head is the open discharge behind RV1 (set 300 kPa). Open, each needs the loop's level
    above what RV1 closed allows (setpoints 350 and 340 kPa), so the free-level search lets go
    RV1 and applies its rule at the levels the PSVs hold: EPANET 2.2 cvstatus with the cracking
    head h_set = Δp_s/(ρ g), the difference there above it, so it opens. The solve ends at a
    state every rule holds: no flow, RV1 at its switch (its inlet at the set)."""
    from opensolve_pipe.services.solver import status

    seen: list[tuple[float, float, Status]] = []
    inside = [False]
    level_changes, check = status._level_changes, status.check_valve_status

    def levelled(*args: Any, **kwargs: Any) -> Any:
        inside[0] = True
        try:
            return level_changes(*args, **kwargs)
        finally:
            inside[0] = False

    def rule(old: Status, dh: float, q: float, cracking: float) -> Status:
        new = check(old, dh, q, cracking)
        if inside[0]:
            seen.append((dh, cracking, new))
        return new

    monkeypatch.setattr(status, "_level_changes", levelled)
    monkeypatch.setattr(status, "check_valve_status", rule)

    def psv(cid: str, setpoint: float) -> dict[str, Any]:
        return {**gate(cid, "active"), "valveType": "psv", "setpoint": setpoint}

    comps = [pump(), tee("T1"), relief(set_pressure=3.0e5), psv("PSV1", 3.5e5), psv("PSV2", 3.4e5)]
    comps.append(
        {
            "type": "reference_node",
            "referenceType": "ideal",
            "id": "N1",
            "name": "N1",
            "elevation": 0.0,
            "pressure": 0.0,
            "ports": [{"id": "port_1", "nominalSize": 0.08}],
        }
    )
    conns = [
        connection("L1", ("PU", "discharge"), ("T1", "run_inlet"), length=150.0, diameter=0.1023),
        connection("L2", ("T1", "run_outlet"), ("PSV1", "inlet"), length=10.0, diameter=0.1023),
        connection("L3", ("PSV1", "outlet"), ("PSV2", "inlet"), length=10.0, diameter=0.1023),
        connection("L4", ("PSV2", "outlet"), ("PU", "suction"), length=130.0, diameter=0.1023),
        connection("B1", ("T1", "branch"), ("RV1", "inlet"), length=2.0, diameter=D_IN),
        connection("B2", ("RV1", "outlet"), ("N1", "port_1"), length=1.0, diameter=D_OUT),
    ]
    state = solve_project(make_project(comps, conns, pump_library=[CURVE]))
    h_set = 3.0e5 / (RHO * g)
    assert seen, "the free-level search never applied RV1's rule"
    for dh, cracking, new in seen:
        assert cracking == pytest.approx(h_set, rel=1e-15)
        if dh > h_set + 1e-4:  # Htol: cvstatus opens it
            assert new is Status.OPEN
    assert any(new is Status.OPEN for *_, new in seen)
    assert state.converged, state.convergence.message
    r = state.relief_valve_results["RV1"]
    assert (r.state, r.flow) == ("closed", 0.0)
    assert r.inlet_pressure is not None
    assert r.back_pressure is not None
    assert r.inlet_pressure - r.back_pressure <= 3.0e5 + RHO * g * 1e-4
    assert r.inlet_pressure == pytest.approx(3.0e5, rel=1e-9)


def test_each_capacity_kind_resolves_its_area_and_coefficient() -> None:
    """Decision 7, §2.2: a letter's API 526 area with Kd 0.65; an effective area with Kd 0.65
    and its covering letter; a certified area and rated coefficient as entered, its overpressure
    as entered (null on ASME's default, which the result's overpressure gives)."""
    effective = solve_project(series(7.0e5, relief(capacity={"kind": "effective", "area": 3.0e-4})))
    cap = effective.relief_valve_results["RV1"].capacity
    assert cap.kind == "effective"
    # 3×10⁻⁴ m² lies between F's 1.98×10⁻⁴ and G's 3.25×10⁻⁴ m² (API 526 via fluids)
    assert (cap.area, cap.discharge_coefficient, cap.covering_letter) == (3.0e-4, KD, "G")
    certified = {"kind": "certified", "area": 2.5e-4, "dischargeCoefficient": 0.7}
    on_default = solve_project(series(7.0e5, relief(capacity=certified)))
    r = on_default.relief_valve_results["RV1"]
    assert r.capacity.kind == "certified"
    assert (r.capacity.area, r.capacity.discharge_coefficient, r.capacity.overpressure) == (
        2.5e-4,
        0.7,
        None,
    )
    assert (r.overpressure, r.overpressure_source) == (0.1, "asme_default")
    own = solve_project(series(7.0e5, relief(capacity={**certified, "overpressure": 0.08})))
    r = own.relief_valve_results["RV1"]
    assert r.capacity.kind == "certified"
    assert (r.capacity.overpressure, r.overpressure, r.overpressure_source) == (0.08, 0.08, "user")
    assert r.full_lift_flow == pytest.approx(0.7 * 2.5e-4 * math.sqrt(2.0 * 5.4e5 / RHO), rel=1e-15)


# --------------------------------------------------------------------------- trace and methods


def _input(trace: Any, start: str) -> Any:
    return next(i for i in trace.inputs if i.name.startswith(start))


def _value(trace: Any, start: str) -> Any:
    return next(v for v in trace.intermediates if v.name.startswith(start))


def test_the_trace_gives_the_sources_the_readings_and_the_gauge_set_overpressure() -> None:
    """§4.1: the set (user), the status (default), a letter's area and Kd (library), ASME's
    overpressure (default); the readings not used, each with its flow at the solved pressures;
    with a back pressure, the overpressure on the gauge set op (Δp_s + p_out)/Δp_s; the
    inequality that set its state; the named departures."""
    state = solve_project(network_m(1.05e6))
    r = state.relief_valve_results["RV1"]
    trace = state.trace.elements["RV1"]
    assert trace.element_type == "relief_valve"
    assert _input(trace, "Set pressure Δp_s").source == "user"
    assert _input(trace, "Status").source == "default"
    assert _input(trace, "API 526 effective area A (letter F)").source == "library"
    assert _input(trace, "API 526 effective area A (letter F)").value == A_F
    assert _input(trace, "Effective coefficient of discharge Kd").source == "library"
    assert _input(trace, "Overpressure at full lift op (ASME").source == "default"
    assert r.inlet_pressure is not None
    assert r.back_pressure is not None
    static = r.inlet_pressure - r.back_pressure
    v_in = r.flow / _area(D_IN)
    stagnation = static + RHO * v_in**2 / 2.0
    assert _value(trace, "Pressure difference by the static reading").value == pytest.approx(
        static, rel=1e-12
    )
    assert _value(trace, "Flow the static reading would give").value == pytest.approx(
        law_flow(KD * A_F, 5.0e5, 0.1, static), rel=1e-12
    )
    assert _value(trace, "Flow the definitions' reading would give").value == pytest.approx(
        law_flow(KD * A_F, 5.0e5, 0.1, stagnation), rel=1e-12
    )
    assert _value(trace, "Flow the static reading would give").value / r.flow - 1.0 == (
        pytest.approx(-0.01609, abs=5e-6)  # C2: the static reading, −1.609 %
    )
    assert _value(trace, "Pressure difference by the definitions' reading").value == (
        pytest.approx(stagnation, rel=1e-12)
    )
    assert _value(trace, "Flow the definitions' reading would give").value / r.flow - 1.0 == (
        pytest.approx(0.00418, abs=5e-6)  # C2: the stagnation reading, +0.418 %
    )
    gauge_set = _value(trace, "Overpressure on the set difference that would put full lift")
    assert gauge_set.value == pytest.approx(0.1 * (5.0e5 + r.back_pressure) / 5.0e5, rel=1e-12)
    assert _value(trace, "Head loss by the law h(Q)").value == pytest.approx(r.head_loss, rel=1e-9)
    notes = " ".join(trace.notes)
    assert "Open, partial lift" in notes
    assert "Pentair's typical liquid-trim lift characteristic (TP-V300 Fig. 4-12)" in notes
    assert "The overpressure is taken on the set difference" in notes
    assert "Kw = Kc = Kv = 1" in notes
    assert (
        "a check valve's cracking pressure reads the difference of the energy grade lines" in notes
    )
    names = [c.name for c in trace.correlations]
    assert "Linear lift from the set to full lift (a convention)" in names


def test_a_closed_valves_trace_states_its_inequality_without_the_laws_head() -> None:
    """§4.1: closed, the inequality that kept it closed; the law's head at zero flow is not
    shown beside the solved difference (the link is out of the network)."""
    state = solve_project(series(4.0e5))
    trace = state.trace.elements["RV1"]
    assert any(n.startswith("Closed: Δp_t") for n in trace.notes)
    assert not [v for v in trace.intermediates if v.name.startswith("Head loss by the law")]
    certified = {
        "kind": "certified",
        "area": 2.5e-4,
        "dischargeCoefficient": 0.7,
        "overpressure": 0.08,
    }
    own = solve_project(series(4.0e5, relief(capacity=certified))).trace.elements["RV1"]
    assert _input(own, "Actual orifice area A (certified)").source == "user"
    assert _input(own, "Rated coefficient of discharge K").source == "user"
    assert _input(own, "Overpressure at full lift op (certified").source == "user"
    effective = solve_project(series(4.0e5, relief(capacity={"kind": "effective", "area": 3.0e-4})))
    notes = effective.trace.elements["RV1"].notes
    assert any("covers this area: G (fluids.safety_valve.API520_round_size)" in n for n in notes)


def test_the_trace_gives_asmes_default_by_its_equation_and_the_term_that_set_it() -> None:
    """§4.1: on ASME's default the trace gives op = max(0.1, 3 psi/Δp_s) and names the term that
    sets it at this set, the 3 psi floor at 150 kPa (C5's 0.1378951459) and the 10 % at 500 kPa;
    on a certified overpressure neither. And the full-lift loss coefficient on the inlet pipe's
    bore, K = (A_in/C)², from which Δp_t = K ρ v_in²/2 (for comparison)."""
    floor = solve_project(series(3.0e5, relief(set_pressure=1.5e5))).trace.elements["RV1"]
    [equation] = [e for e in floor.equations if e.startswith("op = max(")]
    assert equation.startswith(f"op = max(0.1, 3 psi/Δp_s), 3 psi = {THREE_PSI:.10g} Pa: ASME's")
    [note] = [n for n in floor.notes if n.startswith("ASME's default overpressure at this set")]
    ratio = THREE_PSI / 1.5e5
    assert ratio == pytest.approx(0.1378951459, rel=1e-9)
    assert note == (
        f"ASME's default overpressure at this set is its 3 psi floor, 3 psi/Δp_s = "
        f"{THREE_PSI:.10g}/150000 = {ratio:.10g} > 0.1: op = {ratio:.10g}."
    )
    ten = solve_project(series(1.05e6)).trace.elements["RV1"]
    [note] = [n for n in ten.notes if n.startswith("ASME's default overpressure at this set")]
    assert note == (
        f"ASME's default overpressure at this set is its 10 %, 3 psi/Δp_s = {THREE_PSI:.10g}/"
        f"500000 = {THREE_PSI / 5.0e5:.10g} < 0.1: op = 0.1."
    )
    k = _value(ten, "Loss coefficient at full lift on the inlet pipe's bore, K = (A_in/C)²")
    assert k.value == pytest.approx((_area(D_IN) / (KD * A_F)) ** 2, rel=1e-14)
    certified = {"kind": "certified", "area": 2.5e-4, "dischargeCoefficient": 0.7}
    own = solve_project(series(1.05e6, relief(capacity={**certified, "overpressure": 0.08})))
    trace = own.trace.elements["RV1"]
    assert not [e for e in trace.equations if e.startswith("op = max(")]
    assert not [n for n in trace.notes if n.startswith("ASME's default overpressure")]


def test_a_valve_open_at_its_switch_is_not_called_open_and_closed() -> None:
    """§12 item 2: the status rule (EPANET 2.2 cvstatus) closes a relief valve only below −Qtol,
    so a valve open at its switch can end with a flow in [−Qtol, 0], which its result labels
    closed; its trace note says that, never "Open, closed". The note is built directly, at a
    flow of −4×10⁻⁹ m³/s with the status open, since which side of zero a solve's flow at the
    switch ends on is round-off."""
    from types import SimpleNamespace

    from opensolve_pipe.services.solver import trace as tr

    project = series(4.0e5)
    data = _built(project).valves["RV1"]
    closed = solve_project(project).relief_valve_results["RV1"]
    h_set = 5.0e5 / (RHO * g)
    result = closed.model_copy(update={"flow": -4.0e-9, "head_loss": h_set})
    controls = {"RV1": SimpleNamespace(status=Status.OPEN)}
    ctx = SimpleNamespace(outer=SimpleNamespace(controls=controls), rho_g=RHO * g)
    t = tr._Trace("RV1", "relief_valve")
    tr._relief_state_note(t, ctx, data, result)  # type: ignore[arg-type]
    [note] = t.build().notes
    assert note.startswith("Open at its switch, reported closed (no forward flow, x = 0): ")
    assert "Q = -4e-09 m³/s ≥ −Qtol = -1e-08 m³/s" in note
    assert "Open, closed" not in note


def test_the_methods_summary_has_a_relief_valves_section_only_with_a_relief_valve() -> None:
    """§4.2: "Relief valves" right after "Valves", and one assumption, only with a relief
    valve; a summary without one is unchanged."""
    summary = methods_summary(_built(series(4.0e5)), "test atmosphere")
    titles = [s.title for s in summary.sections]
    assert titles[titles.index("Valves") + 1] == "Relief valves"
    section = summary.sections[titles.index("Relief valves")]
    text = " ".join(section.items)
    for words in (
        "Three named departures",
        "Fig. 4-12",
        "15 psi (103421 Pa)",
        "never mixed",
        "It starts closed",
        "RELIEF_VALVE_OUT_OF_RANGE",
        "Not applied: API 520's back-pressure correction Kw",
    ):
        assert words in text, words
    assert RELIEF_ASSUMPTION in summary.assumptions
    plain = methods_summary(_built(series(4.0e5, gate("RV1", "active"))), "test atmosphere")
    assert "Relief valves" not in [s.title for s in plain.sections]
    assert RELIEF_ASSUMPTION not in plain.assumptions
    assert [s.title for s in summary.sections if s.title != "Relief valves"] == [
        s.title for s in plain.sections
    ]


# --------------------------------------------------------------------------- scenarios


def _with_scenario(data: dict[str, Any], overrides: list[dict[str, Any]]) -> Project:
    data = dict(data)
    data["scenarios"] = [
        {
            "id": "S1",
            "name": "Blocked",
            "overrides": [{"kind": "component", "componentId": "RV1", **o} for o in overrides],
        }
    ]
    return Project.model_validate(data)


def test_scenario_value_texts_name_each_capacity_kind_and_asmes_default() -> None:
    """§5: a null certified overpressure reads as ASME's default; a whole capacity by its kind,
    in SI, never a dict's repr."""
    assert value_text("capacity.overpressure", None, "") == "ASME's 10 % or 3 psi (the default)"
    assert value_text("capacity", {"kind": "api526", "letter": "J"}, "") == (
        "API 526 J (0.000830321 m²), Kd 0.65 (preliminary)"
    )
    assert value_text("capacity", {"kind": "effective", "area": 4.470709e-4}, "") == (
        "API 520 effective area 0.000447071 m², Kd 0.65 (preliminary)"
    )
    certified = {"kind": "certified", "area": 2.5e-4, "dischargeCoefficient": 0.7}
    assert value_text("capacity", certified, "") == (
        "certified area 0.00025 m², rated coefficient 0.7, overpressure ASME's 10 % or 3 psi "
        "(the default)"
    )
    assert value_text("capacity", {**certified, "overpressure": 0.08}, "").endswith(
        "overpressure 0.08"
    )
    assert value_text("setPressure", 3.5e5, "Pa (difference)") == "350000 Pa"


def test_a_capacity_value_applies_only_to_a_capacity_of_its_kind() -> None:
    """Decision 18: a letter's capacity holds a letter; an effective one an area; a certified
    one an area, a coefficient and an overpressure. A value of another kind is kept and
    ignored, with the reason."""
    letter = _with_scenario(
        series_dict(1.05e6),
        [
            {"field": "capacity.area", "value": 3.0e-4},
            {"field": "capacity.dischargeCoefficient", "value": 0.8},
            {"field": "capacity.letter", "value": "G"},
            {"field": "setPressure", "value": 4.8e5},
        ],
    )
    applied = apply_scenario(letter, "S1")
    states = [(r.state, r.message) for r in applied.overrides]
    assert states[0] == (
        "not_applicable",
        "relief valve RV1 is sized by an API 526 orifice letter in the base project "
        "(capacity.area applies to an API 520 effective area or a certified capacity; set the "
        "whole capacity instead)",
    )
    assert states[1][0] == "not_applicable"
    assert "capacity.dischargeCoefficient applies to a certified capacity" in states[1][1]
    assert states[2:] == [("applied", ""), ("applied", "")]
    valve = next(c for c in applied.project.components if c.id == "RV1")
    assert valve.capacity.kind == "api526"
    assert valve.capacity.letter == "G"
    certified = {
        "kind": "certified",
        "area": 2.5e-4,
        "dischargeCoefficient": 0.7,
        "overpressure": 0.08,
    }
    on_certified = _with_scenario(
        series_dict(1.05e6, relief(capacity=certified)),
        [
            {"field": "capacity.area", "value": 3.0e-4},
            {"field": "capacity.overpressure", "value": None},
            {"field": "capacity.letter", "value": "J"},
        ],
    )
    applied = apply_scenario(on_certified, "S1")
    assert [r.state for r in applied.overrides] == ["applied", "applied", "not_applicable"]
    assert [(r.value, r.base_value, r.unit, r.label) for r in applied.overrides[:2]] == [
        (3.0e-4, 2.5e-4, "m²", "actual orifice area"),
        (None, 0.08, "", "overpressure at full lift"),
    ]
    state, _ = solve_case(on_certified, None, "S1")
    section = state.trace.methods.sections[0]
    assert section.title == "Scenario"
    assert (
        "Component RV1 (relief valve): overpressure at full lift ASME's 10 % or 3 psi (the "
        "default) (base: 0.08)."
    ) in section.items
    r = state.relief_valve_results["RV1"]
    assert (r.overpressure, r.overpressure_source) == (0.1, "asme_default")


def test_a_capacity_value_out_of_bounds_is_located_without_the_union_tag() -> None:
    """D15: a bad value is 400 at its override, never echoed; the location drops the
    capacity union's tag."""
    certified = {"kind": "certified", "area": 2.5e-4, "dischargeCoefficient": 0.7}
    with pytest.raises(ScenarioOverrideError) as caught:
        apply_scenario(
            _with_scenario(
                series_dict(1.05e6, relief(capacity=certified)),
                [{"field": "capacity", "value": {**certified, "dischargeCoefficient": 1.5}}],
            ),
            "S1",
        )
    [issue] = caught.value.issues
    assert issue.message == (
        "body.project.scenarios.0.overrides.0.value.dischargeCoefficient: Input should be less "
        "than or equal to 1"
    )
    assert "1.5" not in issue.message


# --------------------------------------------------------------------------- goal seek


def _goal_seek(
    data: dict[str, Any],
    variables: list[dict[str, Any]],
    goals: list[dict[str, Any]],
    scenario: str | None = None,
) -> gs.GoalSeekOutcome:
    request = GoalSeekRequest.model_validate(
        {
            "project": data,
            "scenarioId": scenario,
            "variables": [{"kind": "component", "componentId": "RV1", **v} for v in variables],
            "goals": goals,
        }
    )
    return gs.goal_seek_case(request)


def test_goal_seek_sizes_an_effective_area_and_names_the_covering_letter() -> None:
    """Decision 19 (G41's use): the effective area that puts the inlet at a target pressure;
    the result's capacity and the Goal seek section name the smallest API 526 letter covering
    the area found."""
    data = series_dict(
        4.4e5, relief(set_pressure=3.5e5, capacity={"kind": "effective", "area": 1e-3})
    )
    out = _goal_seek(
        data,
        [{"field": "capacity.area", "lower": 1e-4, "upper": 1e-2}],
        [{"quantity": "port_pressure", "elementId": "RV1", "portId": "inlet", "target": 3.85e5}],
    )
    assert out.result.met
    [variable] = out.result.variables
    assert variable.scale == "log"
    assert out.state is not None
    found = variable.value
    assert found is not None
    letter = covering_letter(found)
    assert letter is not None
    assert out.state.relief_valve_results["RV1"].capacity.covering_letter == letter
    item = next(i for i in out.result.methods.items if i.startswith("Variable 1"))
    assert f"(the smallest API 526 letter whose effective area covers it: {letter}" in item


def test_goal_seek_starts_a_default_overpressure_in_the_middle_of_its_bounds() -> None:
    """§5: a certified case on ASME's default holds no number: the start is the middle of the
    bounds, and the section names ASME's default as what the case holds."""
    certified = {"kind": "certified", "area": 2.5e-4, "dischargeCoefficient": 0.7}
    out = _goal_seek(
        series_dict(series_pressure(0.0025, 0.7 * 2.5e-4, 5.0e5, 0.1), relief(capacity=certified)),
        [{"field": "capacity.overpressure", "lower": 0.02, "upper": 0.5}],
        [{"quantity": "relief_valve_flow", "elementId": "RV1", "target": 0.0026}],
    )
    [variable] = out.result.variables
    assert (variable.start_source, variable.case_value, variable.base_value) == (
        "middle",
        None,
        None,
    )
    assert variable.start == pytest.approx(0.26, rel=1e-15)
    item = next(i for i in out.result.methods.items if i.startswith("Variable 1"))
    assert (
        "the case's overpressure at full lift is ASME's liquid certification overpressure" in item
    )
    assert out.result.met
    assert out.state is not None
    assert out.state.relief_valve_results["RV1"].flow == pytest.approx(0.0026, rel=0.005)


def test_goal_seek_refuses_values_a_capacity_of_its_kind_does_not_hold() -> None:
    """Decision 19: an area on a letter, an overpressure on an effective area, each 400 at its
    index naming the case's kind; a relief goal on another element is not applicable."""
    with pytest.raises(gs.GoalSeekInputError) as caught:
        _goal_seek(
            series_dict(1.05e6),
            [{"field": "capacity.area", "lower": 1e-4, "upper": 1e-3}],
            [{"quantity": "relief_valve_flow", "elementId": "RV1", "target": 0.002}],
        )
    [issue] = caught.value.issues
    assert issue.code == "VARIABLE_NOT_APPLICABLE"
    assert issue.message == (
        "body.variables.0: the relief valve's capacity is an API 526 orifice letter in this case "
        "(capacity.area applies to an API 520 effective area or a certified capacity)"
    )
    with pytest.raises(gs.GoalSeekInputError) as caught:
        _goal_seek(
            series_dict(1.05e6, relief(capacity={"kind": "effective", "area": 2e-4})),
            [{"field": "capacity.overpressure", "lower": 0.05, "upper": 0.3}],
            [{"quantity": "relief_valve_flow", "elementId": "R1", "target": 0.002}],
        )
    codes = [i.code for i in caught.value.issues]
    assert codes == ["VARIABLE_NOT_APPLICABLE", "GOAL_NOT_APPLICABLE"]
    assert "capacity.overpressure applies to a certified capacity" in caught.value.issues[0].message
    assert caught.value.issues[1].message == (
        "body.goals.0: relief_valve_flow applies to a relief valve, not a reservoir"
    )


def test_goal_seek_builds_the_network_at_each_bound_of_a_relief_variable() -> None:
    """Decision 19: a set box whose lower bound is below 15 psi on a letter is a bounds 400
    located by index, with no id or value; with the same certified valve's overpressure also
    varied every trial writes an overpressure, so the box is not refused."""
    with pytest.raises(gs.GoalSeekInputError) as caught:
        _goal_seek(
            series_dict(1.05e6),
            [{"field": "setPressure", "lower": 5.0e4, "upper": 6.0e5}],
            [{"quantity": "relief_valve_flow", "elementId": "RV1", "target": 0.002}],
        )
    [issue] = caught.value.issues
    assert issue.code == "RELIEF_VALVE_OUT_OF_RANGE"
    assert issue.message.startswith("body.variables.0.lower: the relief valve's set pressure is")
    assert "RV1" not in issue.message
    assert "50000" not in issue.message
    assert issue.component_ids == ["RV1"]
    certified = {"kind": "certified", "area": 2.5e-4, "dischargeCoefficient": 0.7}
    prepared = gs.prepare(
        GoalSeekRequest.model_validate(
            {
                "project": series_dict(1.05e6, relief(capacity=certified)),
                "variables": [
                    {
                        "kind": "component",
                        "componentId": "RV1",
                        "field": f,
                        "lower": lo,
                        "upper": hi,
                    }
                    for f, lo, hi in (
                        ("setPressure", 5.0e4, 6.0e5),
                        ("capacity.overpressure", 0.05, 0.3),
                    )
                ],
                "goals": [
                    {"quantity": "relief_valve_flow", "elementId": "RV1", "target": 0.002},
                    {"quantity": "relief_valve_pressure_drop", "elementId": "RV1", "target": 5e5},
                ],
            }
        )
    )
    assert [v.request.field for v in prepared.variables] == ["setPressure", "capacity.overpressure"]


def test_a_relief_goal_reads_the_result_or_says_why_there_is_none() -> None:
    """§5: relief_valve_flow reads flow, relief_valve_pressure_drop the static drop; a valve
    with no result gives the reason; its state is in goal seek's state map."""
    state = solve_project(network_m(1.05e6))
    flow = Goal.model_validate({"quantity": "relief_valve_flow", "elementId": "RV1", "target": 0.0})
    drop = Goal.model_validate(
        {"quantity": "relief_valve_pressure_drop", "elementId": "RV1", "target": 0.0}
    )
    r = state.relief_valve_results["RV1"]
    assert gs.goal_value(state, flow, "relief valve RV1") == (r.flow, "")
    assert gs.goal_value(state, drop, "relief valve RV1") == (r.pressure_drop, "")
    assert gs._state_map(state)[("RV1", "valve_state")] == ("partial_lift", r.flow)
    floating = solve_project(_closed_loop())
    value, reason = gs.goal_value(floating, flow, "relief valve RV1")
    assert value is None
    assert reason == (
        "relief valve RV1 has no result (a side of it is closed off, or its pressure level is "
        "undetermined)"
    )


def test_a_variable_inside_a_whole_capacity_the_scenario_sets_overrides_the_whole() -> None:
    """D18's rule, generalized (decision 19): an area varied inside a whole capacity that the
    case's scenario sets gets that whole capacity holding the value found, applied it gives the
    reported state, and the scenario's mark names the area; the base's letter is not a value
    of the variable, so its base value is null."""
    data = series_dict(4.4e5, relief(set_pressure=3.5e5))
    data["scenarios"] = [
        {
            "id": "S1",
            "name": "Sized",
            "overrides": [
                {
                    "kind": "component",
                    "componentId": "RV1",
                    "field": "capacity",
                    "value": {"kind": "effective", "area": 1.0e-3},
                }
            ],
        }
    ]
    out = _goal_seek(
        data,
        [{"field": "capacity.area", "lower": 1e-4, "upper": 1e-2}],
        [{"quantity": "port_pressure", "elementId": "RV1", "portId": "inlet", "target": 3.85e5}],
        scenario="S1",
    )
    [variable] = out.result.variables
    assert variable.base_value is None
    assert variable.replaced_override == 0
    assert variable.override is not None
    assert variable.override.field == "capacity"
    assert variable.override.value == {"kind": "effective", "area": variable.value}
    assert out.state is not None
    section = out.state.trace.methods.sections[1]
    assert section.title == "Scenario"
    assert any("the place of its API 520 effective area" in item for item in section.items)


def test_a_set_pressure_keeps_its_base_value_where_the_scenario_changes_the_capacity_kind() -> None:
    """Decision 19: a variable's baseValue is null only for a value inside a capacity the base
    gives by another kind; a set pressure is the same value in every kind, so a scenario that
    changes only the capacity's kind (a letter to an effective area) leaves the set's base value
    the base's, 350 kPa, as goal_seek_check's oracle reads it."""
    data = series_dict(4.4e5, relief(set_pressure=3.5e5))
    data["scenarios"] = [
        {
            "id": "S1",
            "name": "Effective",
            "overrides": [
                {
                    "kind": "component",
                    "componentId": "RV1",
                    "field": "capacity",
                    "value": {"kind": "effective", "area": 1.0e-3},
                }
            ],
        }
    ]
    out = _goal_seek(
        data,
        [{"field": "setPressure", "lower": 2.0e5, "upper": 4.0e5}],
        [{"quantity": "relief_valve_flow", "elementId": "RV1", "target": 0.005}],
        scenario="S1",
    )
    [variable] = out.result.variables
    assert (variable.case_value, variable.base_value) == (3.5e5, 3.5e5)


# --------------------------------------------------------------------------- API, curves, checks


def test_the_api_solves_a_relief_valve_and_refuses_one_outside_asmes_scope() -> None:
    """SDD §5: reliefValveResults in camelCase, always present ({} without relief valves);
    RELIEF_VALVE_OUT_OF_RANGE is 422 TOPOLOGY_ERROR naming the valve."""
    client = _client()
    response = client.post("/api/v1/solve", json={"project": series_dict(1.05e6)})
    assert response.status_code == 200, response.text
    state = response.json()["solvedState"]
    assert state["methodVersion"] == "1.5.0"
    assert state["valveResults"] == {}
    assert list(state["reliefValveResults"]["RV1"]) == [
        "state",
        "flow",
        "lift",
        "headLoss",
        "totalPressureDifference",
        "pressureDrop",
        "inletPressure",
        "backPressure",
        "setPressure",
        "setRatio",
        "overpressure",
        "overpressureSource",
        "fullLiftPressureDifference",
        "fullLiftFlow",
        "flowRatio",
        "capacity",
        "reynoldsNumber",
    ]
    assert state["reliefValveResults"]["RV1"]["capacity"] == {
        "kind": "api526",
        "letter": "F",
        "area": A_F,
        "dischargeCoefficient": KD,
    }
    plain = client.post(
        "/api/v1/solve", json={"project": series_dict(1.05e6, gate("RV1", "active"))}
    )
    assert plain.status_code == 200
    assert plain.json()["solvedState"]["reliefValveResults"] == {}
    bad = client.post(
        "/api/v1/solve", json={"project": series_dict(1.05e6, relief(set_pressure=1.0e5))}
    )
    assert bad.status_code == 422
    body = bad.json()
    assert body["error"] == "TOPOLOGY_ERROR"
    assert [(i["code"], i["componentIds"]) for i in body["issues"]] == [
        ("RELIEF_VALVE_OUT_OF_RANGE", ["RV1"])
    ]


def test_a_system_curve_through_an_opening_relief_valve_holds_its_law() -> None:
    """§3.5: pump → RV1 → R2 gives H_sys(Q) = Δz + Σ h_pipes(Q) + h(Q), with h(0) = h_set (the
    law transcribed here, its band root in decimals). The /system-curve request is cold: its
    points start the relief valve open, as a check valve, so that the pump's fixed flow has its
    way out at every point and the zero-flow point sits at the valve's switch."""
    comps = [reservoir("R1", level=2.0), pump("P1"), relief(set_pressure=2.0e5)]
    comps.append(reservoir("R2", level=4.0))
    conns = [
        connection("L1", ("R1", "port_1"), ("P1", "suction"), length=5.0, diameter=0.1023),
        connection("L2", ("P1", "discharge"), ("RV1", "inlet"), length=10.0, diameter=D_IN),
        connection("L3", ("RV1", "outlet"), ("R2", "port_1"), length=10.0, diameter=D_OUT),
    ]
    project = make_project(comps, conns, pump_library=[CURVE])
    c = KD * A_F
    op = max(0.1, THREE_PSI / 2.0e5)  # 200 kPa is below the 3 psi crossover: 0.1034
    q_full = c * math.sqrt(2.0 * 2.0e5 * (1.0 + op) / RHO)
    points = system_curve(project, "P1", flow_min=0.0, flow_max=1.5 * q_full, num_points=7).points
    assert len(points) == 7
    assert points[0].head == pytest.approx(2.0 + 2.0e5 / (RHO * g), rel=1e-12)
    for point in points:
        q = point.flow
        lines = pipe_loss(q, 0.1023, 5.0) + pipe_loss(q, D_IN, 10.0) + pipe_loss(q, D_OUT, 10.0)
        assert point.head == pytest.approx(2.0 + lines + law_head(c, 2.0e5, op, q), rel=1e-11)


def test_no_design_check_applies_to_a_relief_valve() -> None:
    """Decision 22 (D19): only pipe velocity covers the valve, on its two connections."""
    data = series_dict(1.05e6)
    data["settings"]["designChecks"] = {
        "pipeVelocity": {"maximum": 3.0, "source": {"kind": "user"}},
        "npshMargin": {"minimumMargin": 1.0, "source": {"kind": "user"}},
    }
    state = solve_project(Project.model_validate(data))
    assert {r.check for r in state.design_checks} == {"pipe_velocity"}
    assert [r.connection_id for r in state.design_checks] == ["L1", "L2"]
    assert all(r.component_id is None for r in state.design_checks)
