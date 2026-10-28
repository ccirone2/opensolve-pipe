"""Valve loss coefficients and the valve law (design §2.3, TSD §5.3).

Cv / Kv to K is derived here from the coefficients' definitions and exact unit definitions,
then compared with fluids.fittings.Cv_to_K / Kv_to_K (what the solver calls) and with Crane's
K = 891 d⁴/Cv² (d in inches) quoted in TSD §5.3. Crane default K values are the cited fluids
functions themselves (the source), so they are compared with direct calls.
"""

import math
from typing import Any

import fluids.fittings as ff
import pytest
from fluids.constants import g

from opensolve_pipe.models.components import FlowCoefficient
from opensolve_pipe.services.fluids import fluid_properties
from opensolve_pipe.services.solver.builder import BuiltNetwork, build_network
from opensolve_pipe.services.solver.coefficients import k_from_coefficient
from opensolve_pipe.services.solver.elements import HeadOffsetLaw, ValveLaw
from opensolve_pipe.services.solver.errors import TopologyError
from opensolve_pipe.services.solver.valves import CRANE_DEFAULTS, valve_resistance

from .helpers import connection, custom_pipe, make_project, reservoir

# Exact unit definitions.
INCH = 0.0254  # m (international inch)
LBF = 0.45359237 * 9.80665  # N: pound mass (kg) × standard gravity (m/s²)
PSI = LBF / INCH**2  # Pa
GALLON = 231 * INCH**3  # m³ (US gallon = 231 in³)
GPM = GALLON / 60  # m³/s
BAR = 1.0e5  # Pa
M3_PER_HOUR = 1 / 3600  # m³/s
RHO_REF = 999.29744568
"""kg/m³: the water density fluids uses for its converters, "ρ = 999.29744568 kg/m³ at
T=60° F, P = 703572 Pa ... calculated with IAPWS-95" (fluids.fittings.Kv_to_K docstring)."""


def k_from_definition(q_ref: float, dp_ref: float, diameter: float) -> float:
    """K of a valve passing q_ref [m³/s] of water at dp_ref [Pa]: Δp = K ρ v²/2 with
    v = Q/A gives K = 2 Δp A² / (ρ Q²)."""
    area = math.pi * diameter**2 / 4
    return 2 * dp_ref * area**2 / (RHO_REF * q_ref**2)


def crane_cv_coefficient() -> float:
    """c in K = c d⁴/Cv² with d in inches: K_from_definition(Cv gpm, 1 psi, d inches)."""
    return 2 * PSI * (math.pi / 4) ** 2 * INCH**4 / (RHO_REF * GPM**2)


@pytest.mark.parametrize("d_in", [2.0, 4.0, 8.0])
@pytest.mark.parametrize("cv", [10.0, 250.0])
def test_cv_to_k_from_the_definition(d_in: float, cv: float) -> None:
    d = d_in * INCH
    derived = k_from_definition(cv * GPM, PSI, d)
    assert derived == pytest.approx(crane_cv_coefficient() * d_in**4 / cv**2, rel=1e-13)
    # fluids writes K = 1.6e9 D⁴ / (Cv/1.1560992283536566)², its coefficient rounded to the
    # "very convenient round number" 1.6e9 (7e-11 below the definition at this density).
    assert ff.Cv_to_K(cv, d) == pytest.approx(derived, rel=1e-9)
    assert k_from_coefficient(FlowCoefficient(kind="Cv", value=cv), d)[0] == ff.Cv_to_K(cv, d)


def test_crane_cv_coefficient_is_891_within_two_tenths_of_a_percent() -> None:
    """TSD §5.3 quotes Crane's K = 891 d⁴/Cv²; the definition gives 890.11."""
    assert crane_cv_coefficient() == pytest.approx(891.0, rel=2e-3)


@pytest.mark.parametrize("diameter", [0.05, 0.1023, 0.3])
@pytest.mark.parametrize("kv", [5.0, 400.0])
def test_kv_to_k_from_the_definition(diameter: float, kv: float) -> None:
    derived = k_from_definition(kv * M3_PER_HOUR, BAR, diameter)
    assert ff.Kv_to_K(kv, diameter) == pytest.approx(derived, rel=1e-9)
    assert k_from_coefficient(FlowCoefficient(kind="Kv", value=kv), diameter)[0] == ff.Kv_to_K(
        kv, diameter
    )


def test_k_is_taken_as_entered() -> None:
    k, source = k_from_coefficient(FlowCoefficient(kind="K", value=3.5), 0.1)
    assert (k, source) == (3.5, "user K")


def valve(vtype: str, **kwargs: object) -> dict[str, Any]:
    return {
        "type": "valve",
        "valveType": vtype,
        "id": "V",
        "name": "V",
        "elevation": 0.0,
        "ports": [{"id": "inlet", "nominalSize": 0.1}, {"id": "outlet", "nominalSize": 0.1}],
        **kwargs,
    }


def build(v: dict[str, Any], inlet_pipes: list[dict[str, Any]] | None = None) -> BuiltNetwork:
    comps = [reservoir("R1", level=20.0), v, reservoir("R2", level=10.0)]
    conns = [
        connection("L1", ("R1", "port_1"), ("V", "inlet"), pipes=inlet_pipes),
        connection("L2", ("V", "outlet"), ("R2", "port_1"), diameter=0.08),
    ]
    project = make_project(comps, conns)
    return build_network(project, fluid_properties(project.fluid))


CRANE_CALLS = {
    "gate": lambda d: ff.K_gate_valve_Crane(D1=d, D2=d, angle=0.0),
    "ball": lambda d: ff.K_ball_valve_Crane(D1=d, D2=d, angle=0.0),
    "globe": lambda d: ff.K_globe_valve_Crane(D1=d, D2=d),
    "butterfly": lambda d: ff.K_butterfly_valve_Crane(D=d, style=0),
    "check": lambda d: ff.K_swing_check_valve_Crane(D=d, angled=True),
    "stop_check": lambda d: ff.K_globe_stop_check_valve_Crane(D1=d, D2=d, style=0),
}


@pytest.mark.parametrize("vtype", sorted(CRANE_CALLS))
def test_crane_default_k_is_the_cited_fluids_function(vtype: str) -> None:
    built = build(valve(vtype))
    data = built.valves["V"]
    assert data.reference_diameter == 0.1  # the inlet pipe's inner diameter
    assert data.resistance.k == CRANE_CALLS[vtype](0.1)
    assert data.resistance.crane
    assert data.resistance.origin == "library"
    assert CRANE_DEFAULTS[vtype].call in data.resistance.source
    assert isinstance(data.law, ValveLaw)


@pytest.mark.parametrize("vtype", ["prv", "psv", "fcv"])
def test_control_valves_default_to_ideal(vtype: str) -> None:
    setpoint = 0.01 if vtype == "fcv" else 1.0e5
    data = build(valve(vtype, setpoint=setpoint)).valves["V"]
    assert data.resistance.k == 0.0
    assert data.resistance.origin == "default"
    assert isinstance(data.law, HeadOffsetLaw)  # merged exactly, not floored
    assert data.law.evaluate(0.02) == (0.0, 0.0)


def test_reference_diameter_is_the_inlet_pipes_end_segment() -> None:
    """The inlet connection ends at the valve with its last segment (D = 0.065 m)."""
    pipes = [custom_pipe(10.0, 0.12, 4.5e-5), custom_pipe(5.0, 0.065, 4.5e-5)]
    built = build(valve("gate", resistance={"kind": "Cv", "value": 120.0}), pipes)
    data = built.valves["V"]
    assert data.reference_diameter == 0.065
    assert data.reference_area == pytest.approx(math.pi * 0.065**2 / 4, rel=1e-15)
    assert data.resistance.k == ff.Cv_to_K(120.0, 0.065)
    assert data.outlet_pipe.segment.diameter == 0.08
    assert data.resistance.origin == "user"


def test_cracking_head_applies_to_active_check_valves_only() -> None:
    rho = 998.0  # helpers.custom_fluid default
    active = build(valve("check", crackingPressure=4900.0)).valves["V"]
    assert active.cracking_head == pytest.approx(4900.0 / (rho * g), rel=1e-15)
    locked = build(valve("check", crackingPressure=4900.0, status="locked_open")).valves["V"]
    assert locked.cracking_head == 0.0


@pytest.mark.parametrize("q", [0.02, 0.0, -0.015])
def test_valve_law(q: float) -> None:
    """h = h_c + K Q|Q|/(2 g A²), dh/dQ = 2 K |Q|/(2 g A²), at Q > 0, Q = 0 and Q < 0."""
    k, d, h_c = 4.2, 0.1, 0.35
    area = math.pi * d**2 / 4
    law = ValveLaw(k, area, g, h_c)
    h, slope = law.evaluate(q)
    assert h == pytest.approx(h_c + k * q * abs(q) / (2 * g * area**2), rel=1e-14)
    assert slope == pytest.approx(2 * k * abs(q) / (2 * g * area**2), rel=1e-14, abs=0.0)
    assert law.loss(q) == pytest.approx(k * q * abs(q) / (2 * g * area**2), rel=1e-14)


def test_valve_law_needs_a_positive_k() -> None:
    with pytest.raises(ValueError, match="K > 0"):
        ValveLaw(0.0, 0.01, g)


def test_valve_resistance_for_a_user_k_skips_the_crane_default() -> None:
    from opensolve_pipe.models.components import IsolationValve

    v = IsolationValve.model_validate(valve("globe", resistance={"kind": "K", "value": 2.0}))
    res = valve_resistance(v, 0.1)
    assert (res.k, res.origin, res.crane) == (2.0, "user", False)


@pytest.mark.parametrize(
    ("vtype", "d", "flagged"),
    [
        ("butterfly", 0.025, True),
        ("butterfly", 0.1, False),
        ("butterfly", 0.6, False),
        ("butterfly", 0.9, True),
        ("gate", 0.025, False),  # no size table: K = 8 ft_Crane(D) at any size
    ],
)
def test_crane_default_outside_its_size_table_is_flagged(
    vtype: str, d: float, flagged: bool
) -> None:
    """K_butterfly_valve_Crane tabulates its multiplier for 2"-8", 10"-14" and 16"-24" only
    (fluids 1.3.1 docstring), comparing D with those sizes in inches (its class splits at
    0.2286 m = 9" and 0.381 m = 15"): a default butterfly K outside 2"-24" (scipy.constants
    inch) is still the fluids value, but flagged."""
    from scipy.constants import inch

    built = build(valve(vtype), inlet_pipes=[custom_pipe(100.0, d, 4.5e-5)])
    data = built.valves["V"]
    assert data.resistance.k == CRANE_CALLS[vtype](d)
    if vtype == "butterfly":
        assert (not 2 * inch <= d <= 24 * inch) is flagged
    found = [
        f
        for f in built.network.flags
        if f.code == "CORRELATION_OUT_OF_RANGE" and f.component_id == "V"
    ]
    assert bool(found) is flagged
    assert all(f.severity == "warning" for f in found)


def _loss_coefficient(cv: float, d: float) -> float:
    """K/(2 g A²) of a Cv on an inner diameter d, from the definition (ISA-75.01.01)."""
    k = ff.Cv_to_K(cv, d)
    return float(k / (2.0 * g * (0.25 * math.pi * d * d) ** 2))


@pytest.mark.parametrize(
    ("resistance", "pipes"),
    [
        # Cv_to_K divides by zero, K overflows to inf, Kv_to_K raises OverflowError
        ({"kind": "Cv", "value": 1e-170}, None),
        ({"kind": "Cv", "value": 1e-160}, None),
        ({"kind": "Kv", "value": 1e-160}, None),
        # a finite K whose K/(2 g A²) on a 1 mm inlet pipe overflows
        ({"kind": "Cv", "value": 1e-152}, [custom_pipe(1.0, 1e-3, 0.0)]),
    ],
)
def test_a_valve_resistance_the_solver_cannot_represent_is_a_topology_issue(
    resistance: dict[str, Any], pipes: list[dict[str, Any]] | None
) -> None:
    """A positive Cv or Kv is schema-valid at any size, but one below about 1e-160 crashed the
    build (ZeroDivisionError or OverflowError in the conversion, a 500): it is reported with the
    other topology issues, as a pipe the solver cannot represent is."""
    if pipes is not None:  # the case is what it says
        assert math.isfinite(ff.Cv_to_K(resistance["value"], 1e-3))
        assert _loss_coefficient(resistance["value"], 1e-3) == math.inf
    with pytest.raises(TopologyError) as err:
        build(valve("gate", resistance=resistance), pipes)
    assert [(i.code, i.component_ids) for i in err.value.issues] == [
        ("VALVE_RESISTANCE_OUT_OF_RANGE", ["V"])
    ]
    assert f"{resistance['kind']} of {resistance['value']:g}" in err.value.issues[0].message


def test_a_huge_but_finite_valve_resistance_still_builds() -> None:
    """Cv = 1e-100 (K about 1e204 on 0.1 m) is representable: the valve is built as entered."""
    assert math.isfinite(_loss_coefficient(1e-100, 0.1))
    built = build(valve("gate", resistance={"kind": "Cv", "value": 1e-100}))
    assert built.valves["V"].resistance.k == ff.Cv_to_K(1e-100, 0.1)
