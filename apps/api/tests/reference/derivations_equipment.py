"""Closed-form expected results for the equipment element (docs/proposals/equipment-pressure-drop.md
§7.1; CLAUDE.md D6, D7).

Written from the proposal (§1.1, §1.2 decisions 3-9 and 22, §2, §3.1-§3.3, §7.1), the models
and the cited libraries by a tester who did not read ``opensolve_pipe.services``; nothing here
imports it. Every rating, pipe, elevation, level and fluid is a test input.

Law (proposal §1.1, decisions 4-6 and 22; ``element_laws.equipment_coefficient``). Between its
inlet and outlet ports an equipment item takes a loss of total pressure, on the EGL (D7):

    EGL_inlet − EGL_outlet = h(Q) = c Q|Q|,   c = ΔP_ref / (ρ_ref g Q_ref²)

with (ΔP_ref, Q_ref, ρ_ref) the rated point: as entered for a rating of kind 'point' (the
datasheet's loss ΔP_r at its flow Q_r, inlet → outlet, for a fluid of density ρ_r), and for a Cv
or Kv its definition, 1 psi at Cv US gpm or 1 bar at Kv m³/h of water (ISA-75.01.01; the
reference water ρ_w = CoolProp IAPWS-95 at 60 °F and 703572 Pa, the conditions
fluids.fittings.Kv_to_K documents). The operating density cancels out of the head law; it only
converts head to pressure, so the loss in pressure is ρ g h = ΔP_ref (ρ/ρ_ref)(Q/Q_ref)², the
square law with density scaling of ISA-75.01.01-2007 eq. (1) (the owner's "flow² and density").
The law is odd in Q (decision 6), and no pipe diameter enters it.

Results (proposal §2.2): ``pressureLoss`` = ρ g (EGL_in − EGL_out); ``pressureDrop`` = the static
p_in − p_out, each p = ρ g (EGL − z_port − v²/2g) with v in the connected pipe's end segment
(D7), so

    pressureDrop = ρ g h + ρ g (z_out − z_in) + ρ (v_out² − v_in²)/2      (§3.3)

which every case checks as a guard. ``flowRatio`` = Q/Q_r, null for a Cv or Kv (§2.2).

Flags (§3.2, decision 9): reverse flow (Q < 0) and laminar flow in a connected pipe
(0 < min(Re_inlet pipe, Re_outlet pipe) < 2000, the end segments) each raise
CORRELATION_OUT_OF_RANGE (warning) on the element; the cases keep every pipe clearly turbulent or
clearly laminar, away from 2000 and 4000.

Pipes: Darcy–Weisbach with the suite's friction factor (``derivations``), Colebrook or EPANET's
Swamee–Jain form (``swamee_jain`` cases, which share their network with an EPANET case,
``generate_epanet_cases``); fittings as in ``line``. "EPANET water" is a custom fluid of
1000 kg/m³ with EPANET's ν = 1.1×10⁻⁵ ft²/s; "liquid A" is the suite's 998 kg/m³, 1 mPa·s.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from scipy.optimize import brentq

from opensolve_pipe.models.components import Equipment, RatedPoint
from opensolve_pipe.models.fluids import BuiltinFluid, CustomFluid
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.pumps import PumpCurve
from tests.reference import derivations as dv
from tests.reference import element_laws as el
from tests.reference.case_format import (
    UNCHECKED,
    Expected,
    FrictionMethod,
    ReferenceCase,
    assigned_flow,
    builtin_glycol,
    builtin_water,
    custom_fluid,
    equipment,
    ideal_tee,
    make_project,
    pump,
    rated_coefficient,
    rated_point,
    reservoir,
)
from tests.reference.derivations_fluids import NPSH_DISCHARGE, NPSH_SUCTION
from tests.reference.derivations_pumps import curve_a, solve_decreasing
from tests.reference.line import Line

MODULE = "derivations_equipment"
G = dv.G
MARGIN = el.STATE_MARGIN

LAW = (
    "equipment loss on the EGL h = c Q|Q|, c = dP_ref/(rho_ref g Q_ref^2) (constant K, "
    "ISA-75.01.01 eq. (1) form)"
)
POINT_LAW = LAW + ", rated point as entered"
COEFFICIENT_LAW = (
    LAW + ", a Cv/Kv the rated point 1 psi at Cv US gpm / 1 bar at Kv m3/h of water at 60 F "
    "(CoolProp IAPWS-95, 703572 Pa; scipy.constants units)"
)
STATIC = "static p = rho g (EGL - z - v^2/2g), v in the connected pipe (D7)"

RATING_WATER_TEMPERATURE = 288.15
"""K: 15 °C, the water the test datasheets are rated on (proposal §7.1)."""


def rating_water_density() -> float:
    """ρ_r of the test datasheets: CoolProp IAPWS-95 water at 15 °C and 101325 Pa
    (``derivations.water_properties``), 999.102621 kg/m³ (the web's "Water at 15 °C" button
    writes the same double, proposal §6.1)."""
    return dv.water_properties(RATING_WATER_TEMPERATURE)[0]


E1_POINT = (50_000.0, 0.015)
"""ΔP_r Pa and Q_r m³/s of the shared element E1 (proposal §7.1; test inputs)."""
E1_KV = 60.0
E1_CV = 90.0
"""The coefficient cases rate E1 Kv 60 or Cv 90 instead (test inputs)."""


def e1_rating() -> RatedPoint:
    return rated_point(*E1_POINT, rating_water_density())


FOOT = 0.3048
"""m per international foot (exact)."""
NU_EPANET = 1.1e-5 * FOOT**2
"""m²/s: EPANET's default kinematic viscosity VISCOS = 1.1e-5 ft²/s (types.h:53)."""
EPANET_DENSITY = 1000.0


def epanet_water() -> CustomFluid:
    """The EPANET cases' water: 1000 kg/m³ at EPANET's ν (``generate_epanet_cases``)."""
    return custom_fluid(
        "Water at EPANET's default viscosity", EPANET_DENSITY, NU_EPANET * EPANET_DENSITY
    )


def liquid_a() -> CustomFluid:
    name, rho, mu = dv.FLUID_A
    return custom_fluid(name, rho, mu)


def meg_30_at_5c() -> BuiltinFluid:
    """Built-in 30 % ethylene glycol at 5 °C (CoolProp INCOMP::MEG, Melinder 2010)."""
    return builtin_glycol("ethylene_glycol", 278.15, 0.3)


def _source(name: str, method: str) -> str:
    return dv.source(name, method, MODULE)


def _pid(name: str) -> str:
    return f"ref-{name.replace('_', '-')}"


# --- Shared pieces ---------------------------------------------------------------------------


def signed_flow(loss: Callable[[float], float], dh: float) -> float:
    """The flow Q, signed like dh, with loss(Q) = dh, for a loss odd in Q and increasing
    (pipes without entrance or exit fittings, and the equipment law): brentq on |dh|."""
    if dh == 0.0:
        return 0.0
    q = dv.solve_flow(loss, abs(dh))
    return q if dh > 0.0 else -q


def port_z(element: Equipment, port_id: str) -> float:
    port = next(p for p in element.ports if p.id == port_id)
    return element.elevation if port.elevation is None else port.elevation


@dataclass(frozen=True)
class Ports:
    """The solved state at an element's two ports: flow inlet → outlet, EGLs, the connected
    pipes' end-segment velocities and Reynolds numbers."""

    q: float
    egl_in: float
    egl_out: float
    v_in: float
    v_out: float
    re_in: float
    re_out: float


def ports(q: float, egl_in: float, egl_out: float, d_in: float, d_out: float, nu: float) -> Ports:
    return Ports(
        q,
        egl_in,
        egl_out,
        dv.velocity(q, d_in),
        dv.velocity(q, d_out),
        dv.reynolds(q, d_in, nu),
        dv.reynolds(q, d_out, nu),
    )


def port_pressures(element: Equipment, at: Ports, rho: float) -> dict[str, float]:
    """Static gauge pressure at each port (D7)."""
    return {
        f"{element.id}:inlet": dv.static_pressure(
            rho, at.egl_in, port_z(element, "inlet"), at.v_in
        ),
        f"{element.id}:outlet": dv.static_pressure(
            rho, at.egl_out, port_z(element, "outlet"), at.v_out
        ),
    }


def equipment_expected(element: Equipment, at: Ports, rho: float) -> dict[str, float | None]:
    """The element's expected result (proposal §2.2), after a guard that the solved EGL drop is
    the law's c Q|Q| (1e-9 m); ``equipment_result`` gives the values."""
    h = at.egl_in - at.egl_out
    law = el.equipment_head(element.rating, at.q)
    if abs(h - law) > 1.0e-9 * max(1.0, abs(law)):
        raise RuntimeError(f"{element.id}: EGL drop {h} is not the law's {law}")
    return equipment_result(element, at, rho)


def equipment_result(element: Equipment, at: Ports, rho: float) -> dict[str, float | None]:
    """The result fields of proposal §2.2 at a solved state (closed-form or EPANET's): flow,
    Q/Q_r (None for a Cv or Kv), the EGL drop, ρg times it and the static drop, after a guard
    that the static drop is the §3.3 identity (1e-9 relative)."""
    rating = element.rating
    h = at.egl_in - at.egl_out
    p = port_pressures(element, at, rho)
    drop = p[f"{element.id}:inlet"] - p[f"{element.id}:outlet"]
    identity = (
        rho * G * h
        + rho * G * (port_z(element, "outlet") - port_z(element, "inlet"))
        + rho * (at.v_out**2 - at.v_in**2) / 2.0
    )
    if abs(drop - identity) > 1.0e-9 * max(1.0, abs(identity)):
        raise RuntimeError(f"{element.id}: static drop {drop} is not the identity's {identity}")
    return {
        "flow": at.q,
        "flowRatio": at.q / rating.flow if isinstance(rating, RatedPoint) else None,
        "headLoss": h,
        "pressureLoss": rho * G * h,
        "pressureDrop": drop,
    }


def equipment_flags(element: Equipment, at: Ports) -> list[dict[str, str]]:
    """CORRELATION_OUT_OF_RANGE (warning) on the element for reverse flow or laminar flow in a
    connected pipe (proposal §3.2, decision 9), one entry for either or both (flags are matched
    on code and component). Guards keep the inequalities clear: a nonzero flow (every case's
    |Q| is above 0.9 L/s, far above the zero-flow rounding), each Reynolds number 1 % or more
    from 2000, and no pipe in the transition zone (which would add TRANSITIONAL_FLOW)."""
    reverse = at.q < 0.0
    re = min(at.re_in, at.re_out)
    for value in (at.re_in, at.re_out):
        if abs(value - dv.RE_LAMINAR) <= 0.01 * dv.RE_LAMINAR:
            raise ValueError(f"{element.id}: Re = {value:.0f} is too close to 2000")
        if dv.regime(value) == "transitional":
            raise ValueError(f"{element.id}: a connected pipe is transitional (Re = {value:.0f})")
    laminar = 0.0 < re < dv.RE_LAMINAR
    if at.q == 0.0:
        raise ValueError("the equipment cases carry flow")
    return (
        [{"code": "CORRELATION_OUT_OF_RANGE", "componentId": element.id}]
        if reverse or laminar
        else []
    )


def require_regimes(nu: float, pairs: Sequence[tuple[float, Line]], regime: dv.Regime) -> None:
    """Guard: every listed (flow, line) is in ``regime`` at the solution, so the friction law
    and the flags assumed hold."""
    for q, line in pairs:
        dv.require_regime(q, line.d, nu, regime)


def require_above_vapor_pressure(
    pressures: dict[str, float], rho: float, p_vap: float | None, p_atm: float
) -> None:
    """Guard: no BELOW_VAPOR_PRESSURE (invalid, exhaustive): every absolute static pressure
    p + p_atm clears the vapor pressure (0 Pa without one, TSD §5.5) by ρ g MARGIN."""
    threshold = 0.0 if p_vap is None else p_vap
    for key, p in pressures.items():
        if not p + p_atm > threshold + rho * G * MARGIN:
            raise ValueError(f"{key} is too close to the vapor pressure")


# --- A series line: R1 → L1 → element → L2 → R2 -----------------------------------------------


@dataclass(frozen=True)
class Series:
    """R1 (z1, level1) → inlet line L1 → element (inlet → outlet) → outlet line L2 → R2 (z2,
    level2), connections drawn from R1 towards R2."""

    z1: float
    level1: float
    z2: float
    level2: float
    inlet: Line
    outlet: Line
    element: Equipment

    @property
    def h1(self) -> float:
        return self.z1 + self.level1

    @property
    def h2(self) -> float:
        return self.z2 + self.level2

    def loss(self, q: float, nu: float, method: FrictionMethod) -> float:
        """H_R1 − H_R2 at flow q: h_L1(q) + c q|q| + h_L2(q), odd in q."""
        return (
            self.inlet.head_loss(q, nu, method)
            + el.equipment_head(self.element.rating, q)
            + self.outlet.head_loss(q, nu, method)
        )

    def flow(self, nu: float, method: FrictionMethod) -> float:
        """The series flow, signed (negative when R2 holds the higher head), by brentq."""
        return signed_flow(lambda q: self.loss(q, nu, method), self.h1 - self.h2)

    def ports(self, q: float, nu: float, method: FrictionMethod) -> Ports:
        """The element's ports at flow q: EGL_in = H_R1 − h_L1(q), EGL_out = H_R2 + h_L2(q)."""
        return ports(
            q,
            self.h1 - self.inlet.head_loss(q, nu, method),
            self.h2 + self.outlet.head_loss(q, nu, method),
            self.inlet.d,
            self.outlet.d,
            nu,
        )

    def project(
        self,
        pid: str,
        title: str,
        fluid: CustomFluid | BuiltinFluid,
        method: FrictionMethod,
    ) -> Project:
        e = self.element
        return make_project(
            pid,
            title,
            fluid,
            [reservoir("R1", self.z1, self.level1), e, reservoir("R2", self.z2, self.level2)],
            [
                self.inlet.connect("L1", "R1:port_1", f"{e.id}:inlet"),
                self.outlet.connect("L2", f"{e.id}:outlet", "R2:port_1"),
            ],
            friction_method=method,
        )


def series_case(
    *,
    name: str,
    title: str,
    description: str,
    method_text: str,
    series: Series,
    fluid: CustomFluid | BuiltinFluid,
    method: FrictionMethod,
    q: float | None = None,
    regime: dv.Regime = "turbulent",
    flags: Sequence[dict[str, str]] = (),
) -> ReferenceCase:
    """A Series case: the flow from H_R1 − H_R2 = h_L1(Q) + c Q|Q| + h_L2(Q) (brentq), or q as
    given when the case is built to pass it (closure checked: the EGLs stepped from both
    reservoirs meet across the element within 1e-9 m); EGL and static pressure at each port;
    the element's result and flags."""
    rho, mu, p_vap = dv.fluid_state(fluid)
    nu = mu / rho
    if q is None:
        q = series.flow(nu, method)
    elif abs(series.loss(q, nu, method) - (series.h1 - series.h2)) > 1.0e-9:
        raise RuntimeError(f"{name}: the given flow does not close the energy equation")
    require_regimes(nu, [(q, series.inlet), (q, series.outlet)], regime)
    at = series.ports(q, nu, method)
    e = series.element
    pressures = port_pressures(e, at, rho)
    require_above_vapor_pressure(pressures, rho, p_vap, dv.standard_atmosphere_pressure(0.0))
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": q, "L2": q},
        egl={
            "R1:port_1": series.h1,
            f"{e.id}:inlet": at.egl_in,
            f"{e.id}:outlet": at.egl_out,
            "R2:port_1": series.h2,
        },
        pressures=pressures,
        flags=[*equipment_flags(e, at), *flags],
        vapor_pressure=p_vap if isinstance(fluid, BuiltinFluid) else UNCHECKED,
        equipment={e.id: equipment_expected(e, at, rho)},
    )
    return ReferenceCase(
        name=name,
        description=description,
        source=_source(name, method_text),
        project=series.project(_pid(name), title, fluid, method),
        expected=expected,
    )


# --- The cases -------------------------------------------------------------------------------

LINE_IN = Line(0.1023, 60.0)
LINE_OUT = Line(0.1023, 40.0)
"""102.3 mm × 60 m and × 40 m custom pipes, ε = 4.5×10⁻⁵ m, no fittings (test inputs)."""
LINE_Z = 3.0
"""m: E1's elevation on the line (both ports)."""


def line_series(rating: el.EquipmentRating, *, reverse: bool = False) -> Series:
    """The ``equipment_line`` network: R1 (z 10 m, level 2 m: H 12 m) → L1 → E1 (z 3 m) → L2 →
    R2 (z 0, level 1 m: H 1 m); ``reverse`` swaps the heads (R1 H 1 m, R2 H 12 m)."""
    e1 = equipment("E1", LINE_Z, rating)
    if reverse:
        return Series(0.0, 1.0, 10.0, 2.0, LINE_IN, LINE_OUT, e1)
    return Series(10.0, 2.0, 0.0, 1.0, LINE_IN, LINE_OUT, e1)


def equipment_line_project(
    rating: el.EquipmentRating | None = None,
    pid: str = "ref-equipment-line",
    title: str = "Equipment on a line",
) -> Project:
    """The ``equipment_line`` project (EPANET water, Swamee–Jain), for the EPANET cases."""
    series = line_series(e1_rating() if rating is None else rating)
    return series.project(pid, title, epanet_water(), "swamee_jain")


def equipment_rated_point() -> ReferenceCase:
    """The solve gives back the datasheet: liquid A (998 kg/m³) is also the rating fluid
    (ρ_r = 998 kg/m³), and R1's level is set so that Q = Q_r exactly:

        H₁ − H₂ = h_L1(Q_r) + ΔP_r/(ρ_r g) + h_L2(Q_r)      (explicit, Colebrook),

    R2 z 0, level 1 m; R1 z 5 m, level H₁ − 5 m. Both ports at 3 m on equal bores, so the static
    drop is the loss, ΔP_r (ρ = ρ_r) = 50 kPa."""
    fluid = liquid_a()
    rho, mu, _ = dv.fluid_state(fluid)
    nu = mu / rho
    dp_r, q_r = E1_POINT
    rating = rated_point(dp_r, q_r, rho)
    h2 = 0.0 + 1.0
    dh = LINE_IN.head_loss(q_r, nu) + dp_r / (rating.density * G) + LINE_OUT.head_loss(q_r, nu)
    z1 = 5.0
    series = Series(z1, h2 + dh - z1, 0.0, 1.0, LINE_IN, LINE_OUT, equipment("E1", 3.0, rating))
    case = series_case(
        name="equipment_rated_point",
        title="Equipment at its rated point",
        description=(
            "An equipment item rated 50 kPa at 15 L/s on the case's own fluid, between "
            "reservoirs whose heads differ by the pipes' loss plus the rated head at 15 L/s: "
            "verifies that the solve gives back the datasheet (Q = Q_r, loss and static drop "
            "50 kPa)."
        ),
        method_text=(
            POINT_LAW + "; H1 - H2 = h_L1(Q_r) + dP_r/(rho_r g) + h_L2(Q_r) explicit, "
            "Darcy-Weisbach + Colebrook; " + STATIC
        ),
        series=series,
        fluid=fluid,
        method="colebrook",
        q=q_r,
    )
    loss = case.expected.equipment["E1"]["pressureLoss"]
    assert loss is not None
    if abs(loss - dp_r) > 1.0e-9 * dp_r:
        raise RuntimeError("the rated point does not give back its pressure drop")
    return case


def equipment_line() -> ReferenceCase:
    """E1 (50 kPa at 15 L/s, water at 15 °C) on the line, EPANET water, Swamee–Jain:

    H₁ − H₂ = h_L1(Q) + c Q² + h_L2(Q),   c = ΔP_r/(ρ_r g Q_r²)      (brentq)."""
    return series_case(
        name="equipment_line",
        title="Equipment on a line",
        description=(
            "An equipment item rated 50 kPa at 15 L/s (water at 15 C) between two reservoirs, "
            "in water: verifies the square law with density scaling, c = dP_r/(rho_r g Q_r^2), "
            "the EGL at both ports and the result's loss, static drop and flow ratio."
        ),
        method_text=POINT_LAW + "; Darcy-Weisbach + Swamee-Jain lines; brentq; " + STATIC,
        series=line_series(e1_rating()),
        fluid=epanet_water(),
        method="swamee_jain",
    )


DENSE_LIQUID = 1100.0
"""kg/m³: the density-scaling case's custom liquid, at EPANET water's ν (test input)."""


def equipment_density_scaling() -> ReferenceCase:
    """``equipment_line`` with a liquid of 1100 kg/m³ at the same ν: the head law has no ρ (its
    c is the rating's), and Re = vD/ν is unchanged, so Q and every EGL equal equipment_line's,
    while every pressure scales by 1100/1000: the loss is ΔP_r (ρ/ρ_r)(Q/Q_r)² (the owner's
    "flow² and density"; a metamorphic pair, checked in test_derivation_checks)."""
    fluid = custom_fluid("Dense liquid (custom input)", DENSE_LIQUID, NU_EPANET * DENSE_LIQUID)
    return series_case(
        name="equipment_density_scaling",
        title="Equipment in a denser liquid",
        description=(
            "The equipment line in a liquid 10 % denser than water at the same kinematic "
            "viscosity: verifies that the flow and heads are unchanged while the loss and the "
            "static pressures scale with density (dP = dP_r (rho/rho_r)(Q/Q_r)^2)."
        ),
        method_text=POINT_LAW + "; Darcy-Weisbach + Swamee-Jain lines; brentq; " + STATIC,
        series=line_series(e1_rating()),
        fluid=fluid,
        method="swamee_jain",
    )


GLYCOL_FLAGS = ({"code": "NO_VAPOR_PRESSURE"},)
"""CoolProp's INCOMP glycols have no vapor pressure (D9), as in fluid_meg_solution."""


def equipment_density_scaling_glycol() -> ReferenceCase:
    """The ``equipment_line`` network in built-in 30 % MEG at 5 °C (CoolProp INCOMP::MEG,
    Melinder 2010), Colebrook: E1 is rated on water at 15 °C, so its loss is
    ΔP_r (ρ_MEG/ρ_r)(Q/Q_r)² (brentq)."""
    return series_case(
        name="equipment_density_scaling_glycol",
        title="Water-rated equipment in glycol",
        description=(
            "The equipment line in 30 % ethylene glycol at 5 C with the element rated on water "
            "at 15 C: verifies the density scaling of a water rating in another fluid (the "
            "viscosity is not corrected, proposal decision 9)."
        ),
        method_text=(
            POINT_LAW + "; CoolProp INCOMP::MEG[0.3] at 278.15 K; Darcy-Weisbach + Colebrook "
            "lines; brentq; " + STATIC
        ),
        series=line_series(e1_rating()),
        fluid=meg_30_at_5c(),
        method="colebrook",
        flags=GLYCOL_FLAGS,
    )


def equipment_reverse_flow() -> ReferenceCase:
    """``equipment_line`` with the heads swapped (R1 H 1 m, R2 H 12 m): the law is odd, so
    Q = −Q(equipment_line), and the element is flagged CORRELATION_OUT_OF_RANGE (decision 6)."""
    return series_case(
        name="equipment_reverse_flow",
        title="Equipment in reverse flow",
        description=(
            "The equipment line with the higher head at the outlet side: verifies that reverse "
            "flow takes the same square law (odd in Q) and is flagged CORRELATION_OUT_OF_RANGE "
            "on the element (its rating is for inlet to outlet)."
        ),
        method_text=POINT_LAW
        + " (odd in Q); Darcy-Weisbach + Swamee-Jain lines; brentq; "
        + STATIC,
        series=line_series(e1_rating(), reverse=True),
        fluid=epanet_water(),
        method="swamee_jain",
    )


PORTS_IN = Line(0.1023, 30.0)
PORTS_OUT = Line(0.0779, 50.0)
"""The ports-differ lines: a 102.3 mm × 30 m inlet pipe, a 77.9 mm × 50 m outlet pipe."""
PORTS_Z, PORTS_OUTLET_Z = 20.0, 22.0
"""m: E1's elevation (its inlet port) and its outlet port's elevation, 2 m higher."""


def ports_series(level1: float = 5.0) -> Series:
    """R1 (z 25 m, level ``level1``) → PORTS_IN → E1 (z 20 m, outlet port 22 m) → PORTS_OUT →
    R2 (z 0, level 2 m)."""
    e1 = equipment("E1", PORTS_Z, e1_rating(), outlet_elevation=PORTS_OUTLET_Z)
    return Series(25.0, level1, 0.0, 2.0, PORTS_IN, PORTS_OUT, e1)


def equipment_ports_differ() -> ReferenceCase:
    """E1 with its outlet port 2 m above its inlet port and a smaller outlet pipe: the loss is
    still c Q² on the EGL (decision 4), and the static drop is every term of the §3.3 identity,
    ρgh + ρg(z_out − z_in) + ρ(v_out² − v_in²)/2."""
    return series_case(
        name="equipment_ports_differ",
        title="Equipment with ports at different heights",
        description=(
            "An equipment item whose outlet port is 2 m above its inlet port, with a 77.9 mm "
            "outlet pipe after a 102.3 mm inlet pipe: verifies that the loss stays on the EGL "
            "and that the static pressure drop adds the elevation and velocity-head terms."
        ),
        method_text=(
            POINT_LAW
            + "; Darcy-Weisbach + Swamee-Jain lines; brentq; "
            + STATIC
            + "; dp_static = rho g h + rho g (z_out - z_in) + rho (v_out^2 - v_in^2)/2"
        ),
        series=ports_series(),
        fluid=epanet_water(),
        method="swamee_jain",
    )


# --- A loop: R1 → T1, leg A through E5 beside leg B, T2 → R2 ----------------------------------

LOOP_IN = Line(0.1541, 100.0)
LOOP_A1 = Line(0.1023, 40.0)
LOOP_A2 = Line(0.1023, 40.0)
LOOP_B = Line(0.0779, 120.0)
LOOP_OUT = Line(0.1541, 80.0)
E5_POINT = (80_000.0, 0.020)
"""E5: 80 kPa at 20 L/s, rated on water at 15 °C (test input)."""


@dataclass(frozen=True)
class LoopSolution:
    q: float
    q_a: float
    q_b: float
    h_t1: float
    h_t2: float
    egl_in: float
    egl_out: float


def loop_project(pid: str, title: str) -> Project:
    """R1 (z 15 m, level 5 m) → L1 154.1 mm × 100 m → ideal tee T1 (z 5 m); leg A: T1 run_outlet
    → LA1 102.3 mm × 40 m → E5 (z 6 m) → LA2 102.3 mm × 40 m → T2 run_inlet; leg B: T1 branch →
    LB 77.9 mm × 120 m → T2 branch; ideal tee T2 (z 4 m) → L4 154.1 mm × 80 m → R2 (z 0, level
    2 m). EPANET water, Swamee–Jain."""
    e5 = equipment("E5", 6.0, rated_point(*E5_POINT, rating_water_density()))
    return make_project(
        pid,
        title,
        epanet_water(),
        [
            reservoir("R1", 15.0, 5.0),
            ideal_tee("T1", 5.0),
            e5,
            ideal_tee("T2", 4.0),
            reservoir("R2", 0.0, 2.0),
        ],
        [
            LOOP_IN.connect("L1", "R1:port_1", "T1:run_inlet"),
            LOOP_A1.connect("LA1", "T1:run_outlet", "E5:inlet"),
            LOOP_A2.connect("LA2", "E5:outlet", "T2:run_inlet"),
            LOOP_B.connect("LB", "T1:branch", "T2:branch"),
            LOOP_OUT.connect("L4", "T2:run_outlet", "R2:port_1"),
        ],
        friction_method="swamee_jain",
    )


def solve_loop(rating: el.EquipmentRating, nu: float) -> LoopSolution:
    """Nested brentq: for a total flow Q the split Q_A + Q_B = Q equalizes the legs' losses,
    h_LA1(Q_A) + c Q_A² + h_LA2(Q_A) = h_LB(Q_B) (inner); the outer root uses up the heads,
    H_R1 − H_R2 = h_L1(Q) + h_leg(Q_A(Q)) + h_L4(Q). Ideal tees have one EGL at all ports."""
    method: FrictionMethod = "swamee_jain"
    h1, h2 = 20.0, 2.0

    def leg_a(q: float) -> float:
        return (
            LOOP_A1.head_loss(q, nu, method)
            + el.equipment_head(rating, q)
            + LOOP_A2.head_loss(q, nu, method)
        )

    def split(q: float) -> float:
        root: float = brentq(
            lambda qa: leg_a(qa) - LOOP_B.head_loss(q - qa, nu, method),
            0.0,
            q,
            xtol=1.0e-18,
            rtol=1.0e-15,
            maxiter=500,
        )
        return root

    def energy(q: float) -> float:
        return (
            h1
            - h2
            - LOOP_IN.head_loss(q, nu, method)
            - leg_a(split(q))
            - LOOP_OUT.head_loss(q, nu, method)
        )

    q = solve_decreasing(energy)
    q_a = split(q)
    q_b = q - q_a
    h_t1 = h1 - LOOP_IN.head_loss(q, nu, method)
    h_t2 = h2 + LOOP_OUT.head_loss(q, nu, method)
    egl_in = h_t1 - LOOP_A1.head_loss(q_a, nu, method)
    egl_out = h_t2 + LOOP_A2.head_loss(q_a, nu, method)
    if abs(egl_in - egl_out - el.equipment_head(rating, q_a)) > 1.0e-9:
        raise RuntimeError("leg A does not close")
    if abs(h_t1 - h_t2 - LOOP_B.head_loss(q_b, nu, method)) > 1.0e-9:
        raise RuntimeError("leg B does not close")
    return LoopSolution(q, q_a, q_b, h_t1, h_t2, egl_in, egl_out)


def equipment_in_loop() -> ReferenceCase:
    """E5 on one leg of a loop beside a bypass leg (``solve_loop``)."""
    name = "equipment_in_loop"
    project = loop_project(_pid(name), "Equipment in a loop")
    rho, mu, _ = dv.fluid_state(project.fluid)
    nu = mu / rho
    e5 = next(c for c in project.components if isinstance(c, Equipment))
    sol = solve_loop(e5.rating, nu)
    require_regimes(
        nu,
        [
            (sol.q, LOOP_IN),
            (sol.q_a, LOOP_A1),
            (sol.q_a, LOOP_A2),
            (sol.q_b, LOOP_B),
            (sol.q, LOOP_OUT),
        ],
        "turbulent",
    )
    at = ports(sol.q_a, sol.egl_in, sol.egl_out, LOOP_A1.d, LOOP_A2.d, nu)
    tees = {f"{t}:{p}": h for t, h in (("T1", sol.h_t1), ("T2", sol.h_t2)) for p in TEE_PORTS}
    pressures = port_pressures(e5, at, rho)
    # Each tee port's static pressure with the velocity in its own connected pipe (D7).
    tee_ports = {
        "T1:run_inlet": (5.0, LOOP_IN.velocity(sol.q)),
        "T1:run_outlet": (5.0, LOOP_A1.velocity(sol.q_a)),
        "T1:branch": (5.0, LOOP_B.velocity(sol.q_b)),
        "T2:run_inlet": (4.0, LOOP_A2.velocity(sol.q_a)),
        "T2:branch": (4.0, LOOP_B.velocity(sol.q_b)),
        "T2:run_outlet": (4.0, LOOP_OUT.velocity(sol.q)),
    }
    for key, (z, v) in tee_ports.items():
        pressures[key] = dv.static_pressure(rho, tees[key], z, v)
    require_above_vapor_pressure(pressures, rho, None, dv.standard_atmosphere_pressure(0.0))
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": sol.q, "LA1": sol.q_a, "LA2": sol.q_a, "LB": sol.q_b, "L4": sol.q},
        egl={
            "R1:port_1": 20.0,
            **tees,
            "E5:inlet": sol.egl_in,
            "E5:outlet": sol.egl_out,
            "R2:port_1": 2.0,
        },
        pressures=pressures,
        flags=equipment_flags(e5, at),
        equipment={"E5": equipment_expected(e5, at, rho)},
    )
    return ReferenceCase(
        name=name,
        description=(
            "An equipment item on one leg of a loop beside a smaller bypass leg, between ideal "
            "tees: verifies the element's square law in a network, the flow split and the EGL "
            "at every node."
        ),
        source=_source(
            name,
            POINT_LAW + "; Darcy-Weisbach + Swamee-Jain; nested brentq (split inside, total "
            "outside); " + STATIC,
        ),
        project=project,
        expected=expected,
    )


TEE_PORTS = ("run_inlet", "run_outlet", "branch")


# --- A dead end: R1 → E7 → an assigned demand -------------------------------------------------

DEMAND_IN = Line(0.1023, 60.0)
DEMAND_OUT = Line(0.0779, 30.0)
E7_POINT = (30_000.0, 0.010)
"""E7: 30 kPa at 10 L/s, rated on water at 15 °C (test input)."""
DEMAND = 0.012
"""m³/s: the assigned demand D (test input)."""


def equipment_assigned_demand() -> ReferenceCase:
    """R1 (z 20 m, level 5 m) → 102.3 mm × 60 m → E7 (z 2 m) → 77.9 mm × 30 m → D, an assigned
    demand of 12 L/s at z 1 m (D12), liquid A, Colebrook. Continuity gives every connection the
    demand, so the heads step from R1 without iteration:
        EGL_in = H_R1 − h_L1(Q_D),  EGL_out = EGL_in − c Q_D²,  H_D = EGL_out − h_L2(Q_D)."""
    name = "equipment_assigned_demand"
    fluid = liquid_a()
    rho, mu, _ = dv.fluid_state(fluid)
    nu = mu / rho
    e7 = equipment("E7", 2.0, rated_point(*E7_POINT, rating_water_density()))
    h1 = 20.0 + 5.0
    q = DEMAND
    require_regimes(nu, [(q, DEMAND_IN), (q, DEMAND_OUT)], "turbulent")
    egl_in = h1 - DEMAND_IN.head_loss(q, nu)
    egl_out = egl_in - el.equipment_head(e7.rating, q)
    h_d = egl_out - DEMAND_OUT.head_loss(q, nu)
    at = ports(q, egl_in, egl_out, DEMAND_IN.d, DEMAND_OUT.d, nu)
    pressures = port_pressures(e7, at, rho)
    pressures["D:port_1"] = dv.static_pressure(rho, h_d, 1.0, DEMAND_OUT.velocity(q))
    require_above_vapor_pressure(pressures, rho, None, dv.standard_atmosphere_pressure(0.0))
    project = make_project(
        _pid(name),
        "Equipment feeding an assigned demand",
        fluid,
        [reservoir("R1", 20.0, 5.0), e7, assigned_flow("D", 1.0, DEMAND)],
        [
            DEMAND_IN.connect("L1", "R1:port_1", "E7:inlet"),
            DEMAND_OUT.connect("L2", "E7:outlet", "D:port_1"),
        ],
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": q, "L2": q},
        egl={"R1:port_1": h1, "E7:inlet": egl_in, "E7:outlet": egl_out, "D:port_1": h_d},
        pressures=pressures,
        flags=equipment_flags(e7, at),
        equipment={"E7": equipment_expected(e7, at, rho)},
    )
    return ReferenceCase(
        name=name,
        description=(
            "An equipment item on a dead-end line to an assigned demand of 12 L/s: verifies "
            "that the element carries the demand with its square-law loss and that its static "
            "drop includes the smaller outlet pipe's velocity head."
        ),
        source=_source(
            name,
            POINT_LAW + "; continuity: every connection carries the demand; heads stepped from "
            "R1, Darcy-Weisbach + Colebrook; " + STATIC,
        ),
        project=project,
        expected=expected,
    )


# --- Cv and Kv ---------------------------------------------------------------------------------


def reference_water_liquid() -> CustomFluid:
    """A custom liquid at the suite's reference water density, ρ_w = CoolProp IAPWS-95 water at
    60 °F and 703572 Pa (``element_laws.REFERENCE_WATER_DENSITY``), μ = 1 mPa·s (test input)."""
    return custom_fluid("Reference water (custom input)", el.REFERENCE_WATER_DENSITY, 1.0e-3)


KV_Z1, KV_Z2, KV_LEVEL2 = 10.0, 0.0, 1.0


def kv_series(rating: el.EquipmentRating, level1: float) -> Series:
    """R1 (z 10 m, level ``level1``) → L1 102.3 mm × 60 m → E1 (z 5 m) → L2 102.3 mm × 40 m →
    R2 (z 0, level 1 m)."""
    e1 = equipment("E1", 5.0, rating)
    return Series(KV_Z1, level1, KV_Z2, KV_LEVEL2, LINE_IN, LINE_OUT, e1)


def kv_definition_level() -> float:
    """R1's level that passes Q₁ = Kv m³/h: H₁ − H₂ = h_L1(Q₁) + 1 bar/(ρ_w g) + h_L2(Q₁)
    (explicit, Colebrook): 1 bar across the element at Kv m³/h of water is Kv's definition."""
    fluid = reference_water_liquid()
    nu = fluid.dynamic_viscosity / fluid.density
    q1 = E1_KV * el.KV_FLOW
    dh = (
        LINE_IN.head_loss(q1, nu)
        + el.KV_PRESSURE_DROP / (fluid.density * G)
        + LINE_OUT.head_loss(q1, nu)
    )
    return KV_Z2 + KV_LEVEL2 + dh - KV_Z1


def equipment_kv_definition() -> ReferenceCase:
    """The solve gives back the definition of Kv: E1 rated Kv 60 in a liquid at the reference
    water's density, R1's level set (``kv_definition_level``) so that Q = Q₁ = 60 m³/h, with
    1 bar across the element (both ports at 5 m, equal bores: the static drop is the loss)."""
    q1 = E1_KV * el.KV_FLOW
    case = series_case(
        name="equipment_kv_definition",
        title="Equipment rated by a Kv at its definition",
        description=(
            "An equipment item rated Kv 60 in water at the Kv's reference density, between "
            "reservoirs whose heads differ by the pipes' loss plus 1 bar at 60 m3/h: verifies "
            "that the solve gives back the definition (Q = 60 m3/h, 1 bar across) and that a "
            "Kv rating needs no pipe diameter."
        ),
        method_text=(
            COEFFICIENT_LAW + "; H1 - H2 = h_L1(Q1) + 1 bar/(rho_w g) + h_L2(Q1), Q1 = Kv m3/h, "
            "explicit, Darcy-Weisbach + Colebrook; " + STATIC
        ),
        series=kv_series(rated_coefficient("Kv", E1_KV), kv_definition_level()),
        fluid=reference_water_liquid(),
        method="colebrook",
        q=q1,
    )
    drop = case.expected.equipment["E1"]["pressureDrop"]
    assert drop is not None
    if abs(drop - el.KV_PRESSURE_DROP) > 1.0e-9 * el.KV_PRESSURE_DROP:
        raise RuntimeError("Kv 60 at 60 m3/h is not 1 bar")
    return case


def equipment_cv_glycol() -> ReferenceCase:
    """The ``equipment_line`` network with E1 rated Cv 90, in built-in 30 % MEG at 5 °C,
    Colebrook: c = 1 psi/(ρ_w g (Cv US gpm)²) (brentq), so ρ g h = (ρ/ρ_w) 1 psi (Q/Cv gpm)²,
    ISA-75.01.01 eq. (1) with ρ₀ = ρ_w."""
    return series_case(
        name="equipment_cv_glycol",
        title="Equipment rated by a Cv in glycol",
        description=(
            "An equipment item rated Cv 90 in 30 % ethylene glycol at 5 C: verifies the Cv "
            "rating as a rated point on water (1 psi at 90 US gpm) scaled to the glycol's "
            "density, without a pipe diameter."
        ),
        method_text=(
            COEFFICIENT_LAW + "; CoolProp INCOMP::MEG[0.3] at 278.15 K; Darcy-Weisbach + "
            "Colebrook lines; brentq; " + STATIC
        ),
        series=line_series(rated_coefficient("Cv", E1_CV)),
        fluid=meg_30_at_5c(),
        method="colebrook",
        flags=GLYCOL_FLAGS,
    )


# --- Laminar flow in a connected pipe (decision 9) --------------------------------------------

OIL = ("Viscous oil (custom input)", 870.0, 1.74e-2)
"""A viscous oil (test input): 870 kg/m³, 17.4 mPa·s (the goal-seek G2 oil)."""
OIL_LINES = (Line(0.0525, 20.0), Line(0.0525, 15.0))
E9_POINT = (5_000.0, 0.002)
"""E9: a strainer rated 5 kPa at 2 L/s on water at 15 °C (test input)."""


def equipment_laminar_flag() -> ReferenceCase:
    """A strainer (z 0.5 m) between two 52.5 mm pipes in a viscous oil, R1 H 1.5 m to R2 H 1 m,
    Re ≈ 1200 in both: the square law
    is used unchanged (no viscosity correction), and laminar flow in a connected pipe raises
    CORRELATION_OUT_OF_RANGE on the element (decision 9, as for a valve's Cv or Kv). The pipes
    are laminar, f = 64/Re (brentq). Not in §7.1's table: the reference case of decision 9's
    flag."""
    name, rho, mu = OIL
    fluid = custom_fluid(name, rho, mu)
    e9 = equipment("E9", 0.5, rated_point(*E9_POINT, rating_water_density()))
    series = Series(1.0, 0.5, 0.0, 1.0, *OIL_LINES, e9)
    case = series_case(
        name="equipment_laminar_flag",
        title="Equipment with laminar flow in its pipes",
        description=(
            "A strainer between two small pipes carrying a viscous oil in laminar flow: "
            "verifies that the constant-K square law is applied unchanged (no viscosity "
            "correction) and that laminar flow in a connected pipe is flagged "
            "CORRELATION_OUT_OF_RANGE on the element."
        ),
        method_text=POINT_LAW + "; Darcy-Weisbach, f = 64/Re (laminar); brentq; " + STATIC,
        series=series,
        fluid=fluid,
        method="colebrook",
        regime="laminar",
    )
    if not case.expected.flags:
        raise ValueError("equipment_laminar_flag must flag laminar flow")
    return case


# --- A suction strainer before a pump (NPSH) --------------------------------------------------

STRAINER_POINT = (10_000.0, 0.030)
"""S: a strainer rated 10 kPa at 30 L/s on water at 15 °C (test input)."""
STRAINER_TAIL = Line(0.1541, 1.0)
"""154.1 mm × 1 m from the strainer to the pump (test input)."""
NPSH_WATER_T, NPSH_SITE = 323.15, 1500.0
NPSH_Z1, NPSH_LEVEL1, NPSH_Z, NPSH_Z2, NPSH_LEVEL2 = 0.0, 2.0, 4.0, 18.0, 2.0
"""npsh_margin_standard_atmosphere's inputs (water at 50 °C, site 1500 m; R1 z 0 level 2 m,
pump at 4 m, R2 z 18 m level 2 m), with the strainer S at the pump's elevation."""


def equipment_suction_strainer_npsh() -> ReferenceCase:
    """npsh_margin_standard_atmosphere with a strainer S on the suction side: R1 → NPSH_SUCTION
    → S (z 4 m) → 154.1 mm × 1 m → PU1 (z 4 m, curve_a) → NPSH_DISCHARGE → R2. The operating
    point solves

        H_R1 − h_suction(Q) − c Q² − h_tail(Q) + H₀(Q) − h_discharge(Q) = H_R2      (brentq),

    and the strainer lowers NPSHa through the suction EGL: NPSHa = (H_s − z_s) +
    (p_atm − p_vap)/(ρg), p_atm = ATMOSPHERE_1976(1500 m).P, margin = NPSHa − NPSHr(Q)."""
    name = "equipment_suction_strainer_npsh"
    fluid = builtin_water(NPSH_WATER_T)
    rho, mu, p_vap = dv.fluid_state(fluid)
    assert p_vap is not None
    nu = mu / rho
    curve: PumpCurve = curve_a()
    s = equipment("S", NPSH_Z, rated_point(*STRAINER_POINT, rating_water_density()))
    h1, h2 = NPSH_Z1 + NPSH_LEVEL1, NPSH_Z2 + NPSH_LEVEL2

    def residual(q: float) -> float:
        return (
            h1
            - NPSH_SUCTION.head_loss(q, nu)
            - el.equipment_head(s.rating, q)
            - STRAINER_TAIL.head_loss(q, nu)
            + el.pump_head(curve, 1.0, q)
            - NPSH_DISCHARGE.head_loss(q, nu)
            - h2
        )

    q = solve_decreasing(residual)
    require_regimes(nu, [(q, NPSH_SUCTION), (q, STRAINER_TAIL), (q, NPSH_DISCHARGE)], "turbulent")
    if not el.pump_in_curve_range(curve, 1.0, q):
        raise ValueError("the operating point must stay inside the curve points")
    egl_in = h1 - NPSH_SUCTION.head_loss(q, nu)
    egl_out = egl_in - el.equipment_head(s.rating, q)
    h_s = egl_out - STRAINER_TAIL.head_loss(q, nu)
    h_d = h2 + NPSH_DISCHARGE.head_loss(q, nu)
    head = el.pump_head(curve, 1.0, q)
    if abs(h_d - h_s - head) > 1.0e-9:
        raise RuntimeError("the pump line does not close")
    p_atm = dv.standard_atmosphere_pressure(NPSH_SITE)
    npsha = (h_s - NPSH_Z) + (p_atm - p_vap) / (rho * G)
    npshr = el.npsh_required(curve, 1.0, q)
    if not npsha - npshr > MARGIN:
        raise ValueError("the case keeps a clear positive NPSH margin (no CAVITATION)")
    at = ports(q, egl_in, egl_out, NPSH_SUCTION.d, STRAINER_TAIL.d, nu)
    pressures = port_pressures(s, at, rho)
    pressures["PU1:suction"] = dv.static_pressure(rho, h_s, NPSH_Z, STRAINER_TAIL.velocity(q))
    pressures["PU1:discharge"] = dv.static_pressure(rho, h_d, NPSH_Z, NPSH_DISCHARGE.velocity(q))
    require_above_vapor_pressure(pressures, rho, p_vap, p_atm)
    project = make_project(
        _pid(name),
        "Suction strainer before a pump",
        fluid,
        [
            reservoir("R1", NPSH_Z1, NPSH_LEVEL1),
            s,
            pump("PU1", NPSH_Z, curve.id),
            reservoir("R2", NPSH_Z2, NPSH_LEVEL2),
        ],
        [
            NPSH_SUCTION.connect("L1", "R1:port_1", "S:inlet"),
            STRAINER_TAIL.connect("L2", "S:outlet", "PU1:suction"),
            NPSH_DISCHARGE.connect("L3", "PU1:discharge", "R2:port_1"),
        ],
        pump_library=[curve],
        site_elevation=NPSH_SITE,
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": q, "L2": q, "L3": q},
        egl={
            "R1:port_1": h1,
            "S:inlet": egl_in,
            "S:outlet": egl_out,
            "PU1:suction": h_s,
            "PU1:discharge": h_d,
            "R2:port_1": h2,
        },
        pressures=pressures,
        flags=equipment_flags(s, at),
        vapor_pressure=p_vap,
        atmospheric_pressure=p_atm,
        pumps={
            "PU1": {
                "status": "running",
                "operatingFlow": q,
                "operatingHead": head,
                "npshAvailable": npsha,
                "npshRequired": npshr,
                "npshMargin": npsha - npshr,
            }
        },
        equipment={"S": equipment_expected(s, at, rho)},
    )
    return ReferenceCase(
        name=name,
        description=(
            "A strainer on a pump's suction line (50 C water, site 1500 m): verifies the "
            "operating point with the strainer's square-law loss and that the strainer lowers "
            "NPSH available through the suction EGL."
        ),
        source=_source(
            name,
            POINT_LAW + "; pump curve PCHIP; Darcy-Weisbach + Colebrook; brentq; NPSHa = "
            "(H_s - z_s) + (p_atm - p_vap)/(rho g), p_atm = fluids ATMOSPHERE_1976(1500 m).P, "
            "CoolProp water (IAPWS-95); " + STATIC,
        ),
        project=project,
        expected=expected,
    )


def npsh_available_without_strainer() -> float:
    """NPSHa of the same pump line without the strainer (proposal §7.1: 5.186774563 m), for the
    derivation check that the strainer lowers it."""
    fluid = builtin_water(NPSH_WATER_T)
    rho, mu, p_vap = dv.fluid_state(fluid)
    assert p_vap is not None
    nu = mu / rho
    curve = curve_a()
    h1, h2 = NPSH_Z1 + NPSH_LEVEL1, NPSH_Z2 + NPSH_LEVEL2

    def residual(q: float) -> float:
        return (
            h1
            - NPSH_SUCTION.head_loss(q, nu)
            - STRAINER_TAIL.head_loss(q, nu)
            + el.pump_head(curve, 1.0, q)
            - NPSH_DISCHARGE.head_loss(q, nu)
            - h2
        )

    q = solve_decreasing(residual)
    h_s = h1 - NPSH_SUCTION.head_loss(q, nu) - STRAINER_TAIL.head_loss(q, nu)
    p_atm = dv.standard_atmosphere_pressure(NPSH_SITE)
    return (h_s - NPSH_Z) + (p_atm - p_vap) / (rho * G)


CASES: tuple[Callable[[], ReferenceCase], ...] = (
    equipment_rated_point,
    equipment_line,
    equipment_density_scaling,
    equipment_density_scaling_glycol,
    equipment_reverse_flow,
    equipment_ports_differ,
    equipment_in_loop,
    equipment_assigned_demand,
    equipment_kv_definition,
    equipment_cv_glycol,
    equipment_laminar_flag,
    equipment_suction_strainer_npsh,
)
"""Proposal §7.1's table (its density-scaling row as two cases, one network each: the denser
liquid and the glycol), the two Cv/Kv cases, and decision 9's laminar flag."""
