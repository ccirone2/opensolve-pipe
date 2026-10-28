"""Closed-form expected results for the orifice plate (docs/proposals/orifice-plate.md §7.1;
CLAUDE.md D6, D7).

Written from the proposal (§1.1, §1.2 decisions 2-17, §2.2, §3.1-§3.7, §7.1, §10), the models and
the cited libraries by a tester who did not read ``opensolve_pipe.services``; nothing here imports
it. Every bore, pipe, elevation, level and fluid is a test input.

Law (proposal §1.1; ``element_laws.OrificeLaw``). Between its inlet and outlet ports a plate takes
ISO 5167-2's permanent pressure loss, on the EGL (D7), with v the inlet pipe's velocity:

    EGL_inlet − EGL_outlet = h(Q) = K(C_L) v|v|/(2g),   K(C) = (S/(Cβ²) − 1)²,
    S = √(1 − β⁴(1 − C²)),  β = d/D,  D the inlet pipe's end-segment bore,

C_L the discharge coefficient at D and D/2 tappings whatever the plate's taps (decision 5):
ISO 5167-2:2003 eq. (4) (Reader-Harris/Gallagher, ``element_laws.orifice_c``) at Re_eff =
max(Re_D, Re_lo), Re_lo = max(5000, 16000β²) (decision 7: held, and flagged, below it); or an
entered C_e: as entered without taps or at D and D/2 taps, and moved from corner or flange taps,
C_L = C_e C_ISO(D and D/2, Re_eff)/C_ISO(taps, Re_eff) (decision 13). The law is odd in Q
(decision 10).

Results (proposal §2.2, ``orifice_result``): ``pressureLoss`` = ρg h; ``pressureDrop`` = the
static p_in − p_out, each p = ρg (EGL − z_port − v²/2g) with v in the connected pipe (D7), so

    pressureDrop = ρg h + ρg (z_out − z_in) + ρ (v_out² − v_in²)/2      (§3.7),

which every case checks as a guard; ``differentialPressure`` = (1 − β⁴)/(C_M² β⁴) ρ v|v|/2 (ISO
eq. 1, ε = 1) at the meter's own taps, C_M ISO's C there held at their own Re_lo, or the entered
C as entered, null without taps (decision 14); ``venaContractaPressure`` = p_up + ρg(z_up −
z_down) − (1 − β⁴)/(C_L² β⁴) ρ v²/2, "up" the port the flow enters (decision 15).

Flags (§3.5, decisions 10-15; ``orifice_flags``): CORRELATION_OUT_OF_RANGE (warning) on the plate,
one per inequality broken, each case naming its ``details.limit``; BELOW_VAPOR_PRESSURE (invalid)
on the plate when the vena contracta's absolute pressure is below the vapor pressure (0 Pa for a
fluid without one). Guards keep every inequality clear of its bound.

Pipes: Darcy–Weisbach with the suite's friction factor (``derivations``), Colebrook or EPANET's
Swamee–Jain form for the networks the EPANET cases share (``generate_epanet_cases``). "Liquid A"
is the suite's 998 kg/m³ at 1 mPa·s; "EPANET water" 1000 kg/m³ at EPANET's ν.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from scipy.optimize import brentq

from opensolve_pipe.models.components import Orifice, OrificeTaps
from opensolve_pipe.models.fluids import BuiltinFluid, CustomFluid
from opensolve_pipe.models.project import Project
from tests.reference import derivations as dv
from tests.reference import element_laws as el
from tests.reference.case_format import (
    UNCHECKED,
    Expected,
    FrictionMethod,
    ReferenceCase,
    builtin_water,
    custom_fluid,
    ideal_tee,
    make_project,
    orifice,
    pump,
    reservoir,
)
from tests.reference.derivations_pumps import curve_a
from tests.reference.line import Line

MODULE = "derivations_orifice"
G = dv.G
MARGIN = el.STATE_MARGIN

LAW = (
    "orifice loss on the EGL h = K(C_L) v|v|/2g, K = (sqrt(1 - b^4 (1 - C^2))/(C b^2) - 1)^2 "
    "(ISO 5167-2 pressure-loss relation, cancellation-free form), C_L = ISO 5167-2:2003 eq. (4) "
    "at D and D/2 tappings at max(Re_D, Re_lo), transcribed in element_laws.rhg_terms"
)
ENTERED_LAW = (
    "orifice loss on the EGL h = K(C_L) v|v|/2g, K = (sqrt(1 - b^4 (1 - C^2))/(C b^2) - 1)^2 "
    "(ISO 5167-2 pressure-loss relation), C_L = the entered C"
)
MOVED_LAW = (
    "orifice loss on the EGL h = K(C_L) v|v|/2g (ISO 5167-2 pressure-loss relation), C_L = C_e "
    "C_ISO(D and D/2)/C_ISO(taps) at max(Re_D, Re_lo), eq. (4) in element_laws.rhg_terms"
)
READING = "reading dp = (1 - b^4)/(C_M^2 b^4) rho v|v|/2 (ISO 5167-2 eq. (1), eps = 1)"
VENA = "p_vc = p_up + rho g (z_up - z_down) - (1 - b^4)/(C_L^2 b^4) rho v^2/2"
STATIC = "static p = rho g (EGL - z - v^2/2g), v in the connected pipe (D7)"

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


VISCOUS_OIL = ("Viscous oil (custom input)", 900.0, 0.06)
"""C6's oil (proposal §7.1): 900 kg/m³, 60 mPa·s (test input)."""
LIGHT_OIL = ("Light oil (custom input)", 870.0, 0.012)
"""C7's oil (proposal §7.1): 870 kg/m³, 12 mPa·s (test input)."""


def _source(name: str, method: str) -> str:
    return dv.source(name, method, MODULE)


def _pid(name: str) -> str:
    return f"ref-{name.replace('_', '-')}"


# --- Shared pieces ---------------------------------------------------------------------------


def signed_flow(loss: Callable[[float], float], dh: float) -> float:
    """The flow Q, signed like dh, with loss(Q) = dh, for a loss odd in Q and increasing (pipes
    without entrance or exit fittings, and the orifice law): brentq on |dh|."""
    if dh == 0.0:
        return 0.0
    q = dv.solve_flow(loss, abs(dh))
    return q if dh > 0.0 else -q


def port_z(element: Orifice, port_id: str) -> float:
    port = next(p for p in element.ports if p.id == port_id)
    return element.elevation if port.elevation is None else port.elevation


@dataclass(frozen=True)
class Ports:
    """The solved state at a plate's two ports: flow inlet → outlet, EGLs and the connected
    pipes' end-segment bores."""

    q: float
    egl_in: float
    egl_out: float
    d_in: float
    d_out: float

    @property
    def v_in(self) -> float:
        return dv.velocity(self.q, self.d_in)

    @property
    def v_out(self) -> float:
        return dv.velocity(self.q, self.d_out)


def law_of(element: Orifice, at: Ports, rho: float, mu: float) -> el.OrificeLaw:
    """The plate's law on its inlet pipe's bore (decision 3) in the case fluid."""
    return el.orifice_law(element, at.d_in, rho, mu)


def port_pressures(element: Orifice, at: Ports, rho: float) -> dict[str, float]:
    """Static gauge pressure at each port (D7)."""
    return {
        f"{element.id}:inlet": dv.static_pressure(
            rho, at.egl_in, port_z(element, "inlet"), at.v_in
        ),
        f"{element.id}:outlet": dv.static_pressure(
            rho, at.egl_out, port_z(element, "outlet"), at.v_out
        ),
    }


def vena_contracta_pressure(element: Orifice, at: Ports, rho: float, mu: float) -> float | None:
    """p_vc, Pa gauge (decision 15): p_up + ρg(z_up − z_down) − (1 − β⁴)/(C_L² β⁴) ρ v²/2, with
    "up" the port the flow enters (the inlet for Q > 0, the outlet for Q < 0) and the vena
    contracta at the elevation of the port the flow leaves by; None at zero flow."""
    if at.q == 0.0:
        return None
    p = port_pressures(element, at, rho)
    up, down = ("inlet", "outlet") if at.q > 0.0 else ("outlet", "inlet")
    p_up = p[f"{element.id}:{up}"]
    drop = law_of(element, at, rho, mu).vena_contracta_drop(at.q)
    return p_up + rho * G * (port_z(element, up) - port_z(element, down)) - drop


def orifice_expected(
    element: Orifice, at: Ports, rho: float, mu: float
) -> dict[str, float | str | None]:
    """The plate's expected result (proposal §2.2), after a guard that the solved EGL drop is the
    law's K(C_L) v|v|/2g (1e-9 m); ``orifice_result`` gives the values."""
    h = at.egl_in - at.egl_out
    law = law_of(element, at, rho, mu).head(at.q)
    if abs(h - law) > 1.0e-9 * max(1.0, abs(law)):
        raise RuntimeError(f"{element.id}: EGL drop {h} is not the law's {law}")
    return orifice_result(element, at, rho, mu)


def orifice_result(
    element: Orifice, at: Ports, rho: float, mu: float
) -> dict[str, float | str | None]:
    """Every field of the plate's result (proposal §2.2) at a solved state (closed-form or
    EPANET's), after a guard that the static drop is the §3.7 identity (1e-9 relative)."""
    law = law_of(element, at, rho, mu)
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
        "headLoss": h,
        "pressureLoss": rho * G * h,
        "pressureDrop": drop,
        "differentialPressure": law.differential(at.q),
        "venaContractaPressure": vena_contracta_pressure(element, at, rho, mu),
        "beta": law.beta,
        "pipeDiameter": at.d_in,
        "boreDiameter": element.bore_diameter,
        "reynoldsNumber": law.reynolds(at.q),
        "dischargeCoefficient": law.c_loss(at.q),
        "coefficientSource": law.source,
        "coefficientReynoldsNumber": law.coefficient_reynolds(at.q),
        "tapCoefficientRatio": law.ratio(at.q),
        "lossCoefficient": law.k(at.q),
        "taps": element.taps,
        "meterDischargeCoefficient": law.c_meter(at.q),
    }


GEOMETRY_CLEARANCE = 1.0e-6
"""Relative clearance of a geometric limit (d, D, β: inputs, compared exactly by the solver)."""
FLOW_CLEARANCE = 0.01
"""Relative clearance of a limit on a solved quantity (Re_D: within D6 of the reference, so 1 %
puts it on the same side for any answer D6 accepts)."""


def _clear(value: float, bound: float, clearance: float, what: str) -> None:
    if abs(value - bound) <= clearance * abs(bound):
        raise ValueError(f"{what} = {value!r} is too close to its limit {bound!r}")


def orifice_flags(
    element: Orifice,
    at: Ports,
    rho: float,
    mu: float,
    p_vap: float | None,
    p_atm: float,
) -> list[dict[str, str]]:
    """The plate's flags (§3.5, decisions 10-15): CORRELATION_OUT_OF_RANGE, one per inequality
    broken, with its ``limit``:

    - boreDiameter, pipeDiameter, beta: eq. (4) used and d < 12.5 mm, D outside [50 mm, 1 m],
      β outside [0.1, 0.75] (decision 11);
    - reynoldsNumber: eq. (4) used and 0 < Re_D < Re_lo of C_L (or the move), or below the
      Re_lo of the plate's own taps wherever eq. (4) is evaluated there: ISO's C_M, or the
      move's denominator C_ISO(taps) at C_L's Re_eff (proposal §12 item 1: below that tap set's
      limit the move uses eq. (4) outside its range);
    - outletDiameter: the outlet pipe's end-segment bore differs from D (decision 12);
    - laminar: an entered C and 0 < Re_D < 2000 (decision 13);
    - reverseFlow: the flow runs outlet → inlet (decision 10);

    and BELOW_VAPOR_PRESSURE on the plate when the vena contracta's absolute pressure is below
    the vapor pressure, or at or below 0 Pa for a fluid without one (decision 15), marked by its
    ``venaContractaAbsolutePressure`` detail. Guards keep each inequality clear of its bound."""
    law = law_of(element, at, rho, mu)
    q = at.q
    if q == 0.0:
        raise ValueError("the orifice cases carry flow")
    out: list[dict[str, str]] = []

    def flag(limit: str) -> None:
        out.append({"code": "CORRELATION_OUT_OF_RANGE", "componentId": element.id, "limit": limit})

    limits = el.ISO_LIMITS
    d, d_pipe, beta = element.bore_diameter, at.d_in, law.beta
    re = law.reynolds(q)
    if law.uses_eq4:
        _clear(d, limits["bore_min"], GEOMETRY_CLEARANCE, "d")
        if d < limits["bore_min"]:
            flag("boreDiameter")
        for bound in (limits["pipe_min"], limits["pipe_max"]):
            _clear(d_pipe, bound, GEOMETRY_CLEARANCE, "D")
        if d_pipe < limits["pipe_min"] or d_pipe > limits["pipe_max"]:
            flag("pipeDiameter")
        for bound in (limits["beta_min"], limits["beta_max"]):
            _clear(beta, bound, GEOMETRY_CLEARANCE, "beta")
        if beta < limits["beta_min"] or beta > limits["beta_max"]:
            flag("beta")
        lows = [law.re_lo_loss]
        if element.taps is not None:  # ISO's C_M, or a moved entered C's denominator
            lows.append(el.orifice_re_lo(element.taps, beta, d_pipe))
        for low in lows:
            _clear(re, low, FLOW_CLEARANCE, "Re_D")
        if any(0.0 < re < low for low in lows):
            flag("reynoldsNumber")
    if at.d_out != at.d_in:
        _clear(at.d_out, at.d_in, GEOMETRY_CLEARANCE, "the outlet bore")
        flag("outletDiameter")
    if law.entered is not None:
        _clear(re, dv.RE_LAMINAR, FLOW_CLEARANCE, "Re_D")
        if 0.0 < re < dv.RE_LAMINAR:
            flag("laminar")
    if q < 0.0:
        flag("reverseFlow")
    p_vc = vena_contracta_pressure(element, at, rho, mu)
    assert p_vc is not None
    threshold = 0.0 if p_vap is None else p_vap
    if abs(p_vc + p_atm - threshold) <= rho * G * MARGIN:
        raise ValueError(f"{element.id}: the vena contracta is too close to the vapor pressure")
    if p_vc + p_atm < threshold:
        out.append(
            {
                "code": "BELOW_VAPOR_PRESSURE",
                "componentId": element.id,
                "detail": "venaContractaAbsolutePressure",
            }
        )
    return out


def require_regimes(nu: float, pairs: Sequence[tuple[float, Line]], regime: dv.Regime) -> None:
    """Guard: every listed (flow, line) is in ``regime`` at the solution."""
    for q, line in pairs:
        dv.require_regime(q, line.d, nu, regime)


def require_above_vapor_pressure(
    pressures: dict[str, float], rho: float, p_vap: float | None, p_atm: float
) -> None:
    """Guard: no port BELOW_VAPOR_PRESSURE (invalid, exhaustive): every absolute static pressure
    p + p_atm clears the vapor pressure (0 Pa without one, TSD §5.5) by ρ g MARGIN."""
    threshold = 0.0 if p_vap is None else p_vap
    for key, p in pressures.items():
        if not p + p_atm > threshold + rho * G * MARGIN:
            raise ValueError(f"{key} is too close to the vapor pressure")


# --- A series line: R1 → L1 → plate → L2 → R2 ---------------------------------------------------


@dataclass(frozen=True)
class Series:
    """R1 (z1, level1, surface pressure p1) → inlet line L1 → plate (inlet → outlet) → outlet
    line L2 → R2 (z2, level2), connections drawn from R1 towards R2."""

    z1: float
    level1: float
    z2: float
    level2: float
    inlet: Line
    outlet: Line
    element: Orifice
    p1: float = 0.0

    def h1(self, rho: float) -> float:
        return self.z1 + self.level1 + self.p1 / (rho * G)

    @property
    def h2(self) -> float:
        return self.z2 + self.level2

    def law(self, rho: float, mu: float) -> el.OrificeLaw:
        return el.orifice_law(self.element, self.inlet.d, rho, mu)

    def loss(self, q: float, rho: float, mu: float, method: FrictionMethod) -> float:
        """H_R1 − H_R2 at flow q: h_L1(q) + h_or(q) + h_L2(q), odd in q."""
        nu = mu / rho
        return (
            self.inlet.head_loss(q, nu, method)
            + self.law(rho, mu).head(q)
            + self.outlet.head_loss(q, nu, method)
        )

    def flow(self, rho: float, mu: float, method: FrictionMethod) -> float:
        """The series flow, signed (negative when R2 holds the higher head), by brentq."""
        return signed_flow(lambda q: self.loss(q, rho, mu, method), self.h1(rho) - self.h2)

    def ports(self, q: float, rho: float, mu: float, method: FrictionMethod) -> Ports:
        """The plate's ports at flow q: EGL_in = H_R1 − h_L1(q), EGL_out = H_R2 + h_L2(q)."""
        nu = mu / rho
        return Ports(
            q,
            self.h1(rho) - self.inlet.head_loss(q, nu, method),
            self.h2 + self.outlet.head_loss(q, nu, method),
            self.inlet.d,
            self.outlet.d,
        )

    def project(
        self, pid: str, title: str, fluid: CustomFluid | BuiltinFluid, method: FrictionMethod
    ) -> Project:
        e = self.element
        return make_project(
            pid,
            title,
            fluid,
            [
                reservoir("R1", self.z1, self.level1, surface_pressure=self.p1),
                e,
                reservoir("R2", self.z2, self.level2),
            ],
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
    method: FrictionMethod = "colebrook",
    q: float | None = None,
    regime: dv.Regime = "turbulent",
) -> ReferenceCase:
    """A Series case: the flow from H_R1 − H_R2 = h_L1(Q) + h_or(Q) + h_L2(Q) (brentq), or q as
    given when the case is built to pass it (closure checked: the EGLs stepped from both
    reservoirs meet across the plate within 1e-9 m); EGL and static pressure at each port; the
    plate's result and flags."""
    rho, mu, p_vap = dv.fluid_state(fluid)
    nu = mu / rho
    if q is None:
        q = series.flow(rho, mu, method)
    elif abs(series.loss(q, rho, mu, method) - (series.h1(rho) - series.h2)) > 1.0e-9:
        raise RuntimeError(f"{name}: the given flow does not close the energy equation")
    require_regimes(nu, [(q, series.inlet), (q, series.outlet)], regime)
    at = series.ports(q, rho, mu, method)
    e = series.element
    pressures = port_pressures(e, at, rho)
    p_atm = dv.standard_atmosphere_pressure(0.0)
    require_above_vapor_pressure(pressures, rho, p_vap, p_atm)
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": q, "L2": q},
        egl={
            "R1:port_1": series.h1(rho),
            f"{e.id}:inlet": at.egl_in,
            f"{e.id}:outlet": at.egl_out,
            "R2:port_1": series.h2,
        },
        pressures=pressures,
        flags=orifice_flags(e, at, rho, mu, p_vap, p_atm),
        vapor_pressure=p_vap if isinstance(fluid, BuiltinFluid) else UNCHECKED,
        orifices={e.id: orifice_expected(e, at, rho, mu)},
    )
    return ReferenceCase(
        name=name,
        description=description,
        source=_source(name, method_text),
        project=series.project(_pid(name), title, fluid, method),
        expected=expected,
    )


# --- C1-C4, C11: the orifice line ------------------------------------------------------------

LINE_IN = Line(0.1023, 60.0)
LINE_OUT = Line(0.1023, 40.0)
"""102.3 mm × 60 m and × 40 m custom pipes, ε = 4.5×10⁻⁵ m, no fittings (test inputs)."""
LINE_OUT_WIDE = Line(0.1541, 40.0)
"""C11's outlet pipe: 154.1 mm × 40 m (test input)."""
LINE_Z = 3.0
"""m: OR1's elevation on the line (both ports)."""
LINE_BORE = 0.05115
"""m: OR1's bore, β = 0.5 on 102.3 mm (test input)."""
ENTERED_C = 0.6
"""C3's entered C (test input)."""


def line_orifice(
    *, taps: OrificeTaps | None = "flange", entered: float | None = None, bore: float = LINE_BORE
) -> Orifice:
    """OR1 on the line: z 3 m, bore 51.15 mm, flange taps by default (C1)."""
    return orifice("OR1", LINE_Z, bore, discharge_coefficient=entered, taps=taps)


def line_series(
    element: Orifice | None = None,
    *,
    reverse: bool = False,
    outlet: Line = LINE_OUT,
    z1: float = 10.0,
    level1: float = 2.0,
) -> Series:
    """The ``orifice_line`` network: R1 (z 10 m, level 2 m: H 12 m) → L1 → OR1 (z 3 m) → L2 →
    R2 (z 0, level 1 m: H 1 m); ``reverse`` swaps the heads (R1 H 1 m, R2 H 12 m)."""
    e = line_orifice() if element is None else element
    if reverse:
        return Series(0.0, 1.0, 10.0, 2.0, LINE_IN, outlet, e)
    return Series(z1, level1, 0.0, 1.0, LINE_IN, outlet, e)


def orifice_line_project(
    fluid: CustomFluid | BuiltinFluid,
    method: FrictionMethod,
    pid: str,
    title: str,
    element: Orifice | None = None,
) -> Project:
    """The ``orifice_line`` project in another fluid or friction mode (the EPANET case)."""
    return line_series(element).project(pid, title, fluid, method)


def orifice_line() -> ReferenceCase:
    """C1: OR1 (β 0.5, flange taps) on the line, liquid A, Colebrook:

    H₁ − H₂ = h_L1(Q) + K(C_L(Re_D)) v²/2g + h_L2(Q)      (brentq),

    C_L at D and D/2 tappings (decision 5), the reading at the flange taps."""
    return series_case(
        name="orifice_line",
        title="Orifice plate on a line",
        description=(
            "A flange-tapped orifice plate of beta 0.5 between two reservoirs: verifies ISO "
            "5167-2's permanent pressure loss with the Reader-Harris/Gallagher coefficient at D "
            "and D/2 tappings, the EGL at both ports, the meter's reading at its flange taps "
            "and the vena contracta pressure."
        ),
        method_text=LAW + "; " + READING + "; " + VENA + "; Darcy-Weisbach + Colebrook "
        "lines; brentq; " + STATIC,
        series=line_series(),
        fluid=liquid_a(),
    )


METER_FLOW = 0.012
"""m³/s: the flow C2's level is built to pass (test input)."""
METER_Z1 = 5.0


def meter_readback_level() -> float:
    """R1's level that passes Q* = 12 L/s through C1's network with R1 at z 5 m:
    H₁ = H₂ + h_L1(Q*) + h_or(Q*) + h_L2(Q*) (explicit)."""
    rho, mu, _ = dv.fluid_state(liquid_a())
    series = line_series(z1=METER_Z1, level1=1.0)
    return series.h2 + series.loss(METER_FLOW, rho, mu, "colebrook") - METER_Z1


def orifice_meter_readback() -> ReferenceCase:
    """C2: C1 with R1 at z 5 m and the level that passes Q* = 12 L/s (``meter_readback_level``):
    the reading at Q* is what fluids' ``differential_pressure_meter_solver`` turns back into
    ρQ* (test_derivation_checks)."""
    return series_case(
        name="orifice_meter_readback",
        title="Orifice meter read back",
        description=(
            "The orifice line with the upstream level set so that the plate passes 12 L/s: "
            "verifies the flange-tap reading at a known flow, which ISO 5167-2's flow equation "
            "reads back as that flow."
        ),
        method_text=LAW + "; " + READING + "; H1 = H2 + h_L1(Q*) + h_or(Q*) + h_L2(Q*) "
        "explicit, Darcy-Weisbach + Colebrook; " + STATIC,
        series=line_series(z1=METER_Z1, level1=meter_readback_level()),
        fluid=liquid_a(),
        q=METER_FLOW,
    )


def orifice_entered_c() -> ReferenceCase:
    """C3: C1's plate without taps (a restriction orifice) with an entered C = 0.6: C_L = C_e,
    K constant (decision 13), no reading."""
    return series_case(
        name="orifice_entered_c",
        title="Restriction orifice with an entered C",
        description=(
            "The orifice line with a plate without pressure taps and an entered discharge "
            "coefficient of 0.6: verifies the entered C held at every flow (a constant K), no "
            "reading, and no ISO 5167-2 range flags."
        ),
        method_text=ENTERED_LAW + "; Darcy-Weisbach + Colebrook lines; brentq; " + STATIC,
        series=line_series(line_orifice(taps=None, entered=ENTERED_C)),
        fluid=liquid_a(),
    )


def orifice_reverse_flow() -> ReferenceCase:
    """C4: C1 with the heads swapped (R1 H 1 m, R2 H 12 m): the law is odd (decision 10), so
    Q = −Q(C1), the reading is signed as the flow, the vena contracta is on the inlet side, and
    the plate is flagged (limit reverseFlow)."""
    return series_case(
        name="orifice_reverse_flow",
        title="Orifice plate in reverse flow",
        description=(
            "The orifice line with the higher head at the outlet side: verifies that reverse "
            "flow takes the same law at the same flow rate, that the reading is signed as the "
            "flow, the vena contracta pressure on the inlet side, and the "
            "CORRELATION_OUT_OF_RANGE flag."
        ),
        method_text=LAW + " (odd in Q); " + READING + "; " + VENA + " (up = the outlet port); "
        "Darcy-Weisbach + Colebrook lines; brentq; " + STATIC,
        series=line_series(reverse=True),
        fluid=liquid_a(),
    )


def orifice_outlet_bore_differs() -> ReferenceCase:
    """C11: C1 with a 154.1 mm × 40 m outlet pipe: the loss is still K(C_L) v_in²/2g on the EGL
    (D7) and the static drop is ρgh − ρ(v_in² − v_out²)/2 (§3.7); flagged (limit
    outletDiameter, decision 12)."""
    return series_case(
        name="orifice_outlet_bore_differs",
        title="Orifice plate into a larger pipe",
        description=(
            "The orifice line with a 154.1 mm outlet pipe after the 102.3 mm inlet pipe: "
            "verifies that the loss stays on the EGL with the inlet pipe's velocity, that the "
            "static pressure drop adds the velocity-head term, and the outlet-bore flag."
        ),
        method_text=LAW + "; Darcy-Weisbach + Colebrook lines; brentq; " + STATIC + "; "
        "dp_static = rho g h + rho (v_out^2 - v_in^2)/2",
        series=line_series(outlet=LINE_OUT_WIDE),
        fluid=liquid_a(),
    )


# --- C5: outside ISO's geometry -----------------------------------------------------------------

SMALL_LINES = (Line(0.0409, 20.0), Line(0.0409, 10.0))
SMALL_BORE = 0.010
"""C5: a 10 mm bore (β 0.2445) on 40.9 mm pipes (test inputs)."""


def orifice_outside_iso_geometry() -> ReferenceCase:
    """C5: R1 (z 0, level 30 m) → 40.9 mm × 20 m → OR1 (z 0, d 10 mm, corner taps) → 40.9 mm ×
    10 m → R2 (z 0, level 0): eq. (4) with its small-pipe term (D < 71.12 mm), solved and
    flagged d < 12.5 mm and D < 50 mm (decision 11)."""
    element = orifice("OR1", 0.0, SMALL_BORE, taps="corner")
    return series_case(
        name="orifice_outside_iso_geometry",
        title="Orifice plate outside ISO 5167-2's geometry",
        description=(
            "A 10 mm corner-tapped plate in a 40.9 mm line: verifies eq. (4) with its "
            "small-pipe term, and that a bore below 12.5 mm and a pipe below 50 mm are solved "
            "and flagged, one CORRELATION_OUT_OF_RANGE per limit."
        ),
        method_text=LAW + " (small-pipe term 0.011 (0.75 - b)(2.8 - D/0.0254)); " + READING + "; "
        "Darcy-Weisbach + Colebrook lines; brentq; " + STATIC,
        series=Series(0.0, 30.0, 0.0, 0.0, *SMALL_LINES, element),
        fluid=liquid_a(),
    )


# --- C6, C7: low Reynolds numbers ---------------------------------------------------------------


def low_re_orifice(bore: float, z: float = 0.5) -> Orifice:
    return orifice("OR1", z, bore, taps="flange")


def orifice_low_reynolds() -> ReferenceCase:
    """C6: C1's pipes and plate (β 0.5, flange taps, z 0.5 m) in a viscous oil (900 kg/m³,
    60 mPa·s), R1 (z 1 m, level 2 m) → R2 (z 0, level 1 m): Re_D ≈ 1018 < 5000, so C_L and C_M
    are held at Re_lo = 5000 (decision 7; the flange limit 170000 β² D = 4348 is below 5000), the
    pipes are laminar (f = 64/Re), and the plate is flagged (limit reynoldsNumber)."""
    name, rho, mu = VISCOUS_OIL
    return series_case(
        name="orifice_low_reynolds",
        title="Orifice plate below ISO's Reynolds number",
        description=(
            "An orifice plate in a viscous oil at a Reynolds number near 1000: verifies that "
            "ISO 5167-2's coefficient is held at its lowest Reynolds number (5000) for the loss "
            "and the reading, and the Reynolds-number flag."
        ),
        method_text=LAW + " (held: Re_eff = max(Re_D, 5000)); " + READING + "; Darcy-Weisbach, "
        "f = 64/Re (laminar); brentq; " + STATIC,
        series=Series(1.0, 2.0, 0.0, 1.0, LINE_IN, LINE_OUT, low_re_orifice(LINE_BORE)),
        fluid=custom_fluid(name, rho, mu),
        regime="laminar",
    )


RE_DEPENDENCE_LINES = (Line(0.1023, 30.0), Line(0.1023, 20.0))
RE_DEPENDENCE_BORE = 0.066495
"""C7: β 0.65 on 102.3 mm (test input)."""


def re_dependence_series() -> Series:
    """C7's network: R1 (z 1, level 3 m) → 102.3 mm × 30 m → OR1 (β 0.65, flange, z 0.5 m) →
    102.3 mm × 20 m → R2 (z 0, level 1 m)."""
    return Series(1.0, 3.0, 0.0, 1.0, *RE_DEPENDENCE_LINES, low_re_orifice(RE_DEPENDENCE_BORE))


def orifice_reynolds_dependence() -> ReferenceCase:
    """C7: a β 0.65 flange-tapped plate in a light oil (870 kg/m³, 12 mPa·s) at Re_D ≈ 12,400,
    inside ISO's range (Re_lo 6760 for C_L, 7348 for C_M): eq. (4)'s Re terms move C by more
    than D6 here, so a C held at another Re misses the flow beyond D6 (test_derivation_checks)."""
    name, rho, mu = LIGHT_OIL
    return series_case(
        name="orifice_reynolds_dependence",
        title="Orifice plate at a low turbulent Reynolds number",
        description=(
            "A beta 0.65 orifice plate in a light oil at a Reynolds number near 12,000: "
            "verifies the Reynolds-number dependence of ISO 5167-2's coefficient, which moves "
            "the flow beyond D6 here."
        ),
        method_text=LAW + "; " + READING + "; Darcy-Weisbach + Colebrook lines; brentq; " + STATIC,
        series=re_dependence_series(),
        fluid=custom_fluid(name, rho, mu),
    )


# --- C8: a balancing loop -----------------------------------------------------------------------

LOOP_IN = Line(0.1541, 100.0)
LOOP_A = Line(0.0779, 40.0)
LOOP_B = Line(0.0779, 60.0)
LOOP_OUT = Line(0.1541, 80.0)
LOOP_BORES = {"ORA": 0.035055, "ORB": 0.04674}
"""β 0.45 and 0.6 on 77.9 mm, no taps (test inputs)."""
LOOP_ORIFICE_Z = 5.0
"""m: both plates' elevation (test input; the flows do not depend on it)."""
TEE_PORTS = ("run_inlet", "run_outlet", "branch")


def loop_project(pid: str, title: str, fluid: CustomFluid, method: FrictionMethod) -> Project:
    """R1 (z 15 m, level 5 m) → L1 154.1 mm × 100 m → ideal tee T1 (z 5 m); leg A: T1 run_outlet
    → LA1 77.9 mm × 40 m → ORA → LA2 77.9 mm × 40 m → T2 run_inlet; leg B: T1 branch → LB1
    77.9 mm × 60 m → ORB → LB2 77.9 mm × 60 m → T2 branch; ideal tee T2 (z 4 m) → L4 154.1 mm ×
    80 m → R2 (z 0, level 2 m)."""
    return make_project(
        pid,
        title,
        fluid,
        [
            reservoir("R1", 15.0, 5.0),
            ideal_tee("T1", 5.0),
            orifice("ORA", LOOP_ORIFICE_Z, LOOP_BORES["ORA"]),
            orifice("ORB", LOOP_ORIFICE_Z, LOOP_BORES["ORB"]),
            ideal_tee("T2", 4.0),
            reservoir("R2", 0.0, 2.0),
        ],
        [
            LOOP_IN.connect("L1", "R1:port_1", "T1:run_inlet"),
            LOOP_A.connect("LA1", "T1:run_outlet", "ORA:inlet"),
            LOOP_A.connect("LA2", "ORA:outlet", "T2:run_inlet"),
            LOOP_B.connect("LB1", "T1:branch", "ORB:inlet"),
            LOOP_B.connect("LB2", "ORB:outlet", "T2:branch"),
            LOOP_OUT.connect("L4", "T2:run_outlet", "R2:port_1"),
        ],
        friction_method=method,
    )


@dataclass(frozen=True)
class LoopSolution:
    q: float
    q_a: float
    q_b: float
    h_t1: float
    h_t2: float


def solve_loop(project: Project, method: FrictionMethod) -> LoopSolution:
    """Nested brentq: for a total flow Q the split Q_A + Q_B = Q equalizes the legs' losses,
    h_LA1(Q_A) + h_ORA(Q_A) + h_LA2(Q_A) = h_LB1(Q_B) + h_ORB(Q_B) + h_LB2(Q_B) (inner); the outer
    root uses up the heads, H_R1 − H_R2 = h_L1(Q) + h_legA(Q_A(Q)) + h_L4(Q). Ideal tees have one
    EGL at all ports."""
    rho, mu, _ = dv.fluid_state(project.fluid)
    nu = mu / rho
    elements = {c.id: c for c in project.components if isinstance(c, Orifice)}
    law_a = el.orifice_law(elements["ORA"], LOOP_A.d, rho, mu)
    law_b = el.orifice_law(elements["ORB"], LOOP_B.d, rho, mu)
    h1, h2 = 20.0, 2.0

    def leg(line: Line, law: el.OrificeLaw, q: float) -> float:
        return 2.0 * line.head_loss(q, nu, method) + law.head(q)

    def split(q: float) -> float:
        root: float = brentq(
            lambda qa: leg(LOOP_A, law_a, qa) - leg(LOOP_B, law_b, q - qa),
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
            - leg(LOOP_A, law_a, split(q))
            - LOOP_OUT.head_loss(q, nu, method)
        )

    q = dv.solve_flow(
        lambda q: (
            LOOP_IN.head_loss(q, nu, method)
            + leg(LOOP_A, law_a, split(q))
            + LOOP_OUT.head_loss(q, nu, method)
        ),
        h1 - h2,
    )
    if abs(energy(q)) > 1.0e-9:
        raise RuntimeError("the loop does not close")
    q_a = split(q)
    q_b = q - q_a
    h_t1 = h1 - LOOP_IN.head_loss(q, nu, method)
    h_t2 = h2 + LOOP_OUT.head_loss(q, nu, method)
    if abs(h_t1 - h_t2 - leg(LOOP_B, law_b, q_b)) > 1.0e-9:
        raise RuntimeError("leg B does not close")
    return LoopSolution(q, q_a, q_b, h_t1, h_t2)


def loop_legs(project: Project, sol: LoopSolution, method: FrictionMethod) -> dict[str, Ports]:
    """Each plate's ports in a loop solution: EGL_in = H_T1 − h_line(Q_leg), EGL_out = H_T2 +
    h_line(Q_leg), on 77.9 mm both sides."""
    rho, mu, _ = dv.fluid_state(project.fluid)
    nu = mu / rho
    out = {}
    for cid, line, q in (("ORA", LOOP_A, sol.q_a), ("ORB", LOOP_B, sol.q_b)):
        out[cid] = Ports(
            q,
            sol.h_t1 - line.head_loss(q, nu, method),
            sol.h_t2 + line.head_loss(q, nu, method),
            line.d,
            line.d,
        )
    return out


def orifice_balancing_loop() -> ReferenceCase:
    """C8: two restriction orifices (β 0.45 and 0.6, no taps) balancing the legs of a loop
    between ideal tees (``solve_loop``), liquid A, Colebrook."""
    name = "orifice_balancing_loop"
    method: FrictionMethod = "colebrook"
    project = loop_project(_pid(name), "Orifice plates balancing a loop", liquid_a(), method)
    rho, mu, p_vap = dv.fluid_state(project.fluid)
    nu = mu / rho
    sol = solve_loop(project, method)
    require_regimes(
        nu,
        [(sol.q, LOOP_IN), (sol.q_a, LOOP_A), (sol.q_b, LOOP_B), (sol.q, LOOP_OUT)],
        "turbulent",
    )
    legs = loop_legs(project, sol, method)
    elements = {c.id: c for c in project.components if isinstance(c, Orifice)}
    tees = {f"{t}:{p}": h for t, h in (("T1", sol.h_t1), ("T2", sol.h_t2)) for p in TEE_PORTS}
    pressures: dict[str, float] = {}
    for cid, at in legs.items():
        pressures |= port_pressures(elements[cid], at, rho)
    tee_ports = {
        "T1:run_inlet": (5.0, LOOP_IN.velocity(sol.q)),
        "T1:run_outlet": (5.0, LOOP_A.velocity(sol.q_a)),
        "T1:branch": (5.0, LOOP_B.velocity(sol.q_b)),
        "T2:run_inlet": (4.0, LOOP_A.velocity(sol.q_a)),
        "T2:branch": (4.0, LOOP_B.velocity(sol.q_b)),
        "T2:run_outlet": (4.0, LOOP_OUT.velocity(sol.q)),
    }
    for key, (z, v) in tee_ports.items():
        pressures[key] = dv.static_pressure(rho, tees[key], z, v)
    p_atm = dv.standard_atmosphere_pressure(0.0)
    require_above_vapor_pressure(pressures, rho, p_vap, p_atm)
    flags = [
        f
        for cid, at in legs.items()
        for f in orifice_flags(elements[cid], at, rho, mu, None, p_atm)
    ]
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={
            "L1": sol.q,
            "LA1": sol.q_a,
            "LA2": sol.q_a,
            "LB1": sol.q_b,
            "LB2": sol.q_b,
            "L4": sol.q,
        },
        egl={
            "R1:port_1": 20.0,
            **tees,
            **{f"{cid}:inlet": at.egl_in for cid, at in legs.items()},
            **{f"{cid}:outlet": at.egl_out for cid, at in legs.items()},
            "R2:port_1": 2.0,
        },
        pressures=pressures,
        flags=flags,
        orifices={cid: orifice_expected(elements[cid], at, rho, mu) for cid, at in legs.items()},
    )
    return ReferenceCase(
        name=name,
        description=(
            "Two restriction orifices of different bores on the two legs of a loop between "
            "ideal tees: verifies the plate law in a network, the flow split it sets and the "
            "EGL at every node."
        ),
        source=_source(
            name,
            LAW
            + "; Darcy-Weisbach + Colebrook; nested brentq (split inside, total outside); "
            + STATIC,
        ),
        project=project,
        expected=expected,
    )


# --- C9: a pump's minimum-flow bypass -----------------------------------------------------------

BYPASS_SUCTION = Line(0.1541, 8.0)
BYPASS_DISCHARGE = Line(0.1023, 5.0)
BYPASS_PROCESS = Line(0.1023, 50.0)
BYPASS_TO_RO = Line(0.0525, 10.0)
BYPASS_FROM_RO = Line(0.0525, 5.0)
BYPASS_BORE = 0.015
"""m: RO, a 15 mm restriction orifice without taps on 52.5 mm (β 0.2857; test input)."""
BYPASS_H1, BYPASS_H2 = 2.0, 20.0
"""m: R1 (z 0, level 2 m) and R2 (z 18 m, level 2 m)."""


def bypass_project(pid: str, title: str, bore: float = BYPASS_BORE) -> Project:
    """R1 (z 0, level 2 m, two ports) → L1 154.1 mm × 8 m → PU1 (z 0.5 m, curve_a) → L2
    102.3 mm × 5 m → ideal tee T1 (z 1 m) → L3 102.3 mm × 50 m → R2 (z 18 m, level 2 m); T1
    branch → LB1 52.5 mm × 10 m → RO (z 1 m) → LB2 52.5 mm × 5 m → R1 port_2. Liquid A."""
    curve = curve_a()
    return make_project(
        pid,
        title,
        liquid_a(),
        [
            reservoir("R1", 0.0, 2.0, ports=("port_1", "port_2")),
            pump("PU1", 0.5, curve.id),
            ideal_tee("T1", 1.0),
            reservoir("R2", 18.0, 2.0),
            orifice("RO", 1.0, bore),
        ],
        [
            BYPASS_SUCTION.connect("L1", "R1:port_1", "PU1:suction"),
            BYPASS_DISCHARGE.connect("L2", "PU1:discharge", "T1:run_inlet"),
            BYPASS_PROCESS.connect("L3", "T1:run_outlet", "R2:port_1"),
            BYPASS_TO_RO.connect("LB1", "T1:branch", "RO:inlet"),
            BYPASS_FROM_RO.connect("LB2", "RO:outlet", "R1:port_2"),
        ],
        pump_library=[curve],
    )


@dataclass(frozen=True)
class BypassSolution:
    h_t1: float
    q_pump: float
    q_process: float
    q_bypass: float


def bypass_pump_side(q: float, nu: float) -> float:
    """H_T1 the pump gives at flow q: H_R1 − h_L1(q) + H₀(q) − h_L2(q) (curve_a, speed 1)."""
    return (
        BYPASS_H1
        - BYPASS_SUCTION.head_loss(q, nu)
        + el.pump_head(curve_a(), 1.0, q)
        - BYPASS_DISCHARGE.head_loss(q, nu)
    )


def bypass_flow(law: el.OrificeLaw, h_t1: float, nu: float) -> float:
    """The bypass flow at T1's EGL: h_LB1(Q) + h_RO(Q) + h_LB2(Q) = H_T1 − H_R1 (brentq)."""
    return signed_flow(
        lambda q: BYPASS_TO_RO.head_loss(q, nu) + law.head(q) + BYPASS_FROM_RO.head_loss(q, nu),
        h_t1 - BYPASS_H1,
    )


def solve_bypass(project: Project) -> BypassSolution:
    """brentq on T1's EGL: the pump's flow at H_T1 (its side, decreasing in Q) equals the
    process flow (L3: h_L3(Q) = H_T1 − H_R2) plus the bypass flow (``bypass_flow``)."""
    rho, mu, _ = dv.fluid_state(project.fluid)
    nu = mu / rho
    ro = next(c for c in project.components if isinstance(c, Orifice))
    law = el.orifice_law(ro, BYPASS_TO_RO.d, rho, mu)

    def demand(h: float) -> float:
        process = signed_flow(lambda q: BYPASS_PROCESS.head_loss(q, nu), h - BYPASS_H2)
        return process + bypass_flow(law, h, nu)

    def residual(h: float) -> float:
        return bypass_pump_side(demand(h), nu) - h

    shutoff = el.shutoff_head(curve_a(), 1.0)
    h: float = brentq(
        residual,
        BYPASS_H2,
        BYPASS_H1 + shutoff,
        xtol=1.0e-15,
        rtol=4.0 * 2.0**-52,
        maxiter=500,
    )
    process = signed_flow(lambda q: BYPASS_PROCESS.head_loss(q, nu), h - BYPASS_H2)
    q_b = bypass_flow(law, h, nu)
    q_p = process + q_b
    if abs(bypass_pump_side(q_p, nu) - h) > 1.0e-9:
        raise RuntimeError("the pump side does not close")
    return BypassSolution(h, q_p, process, q_b)


def orifice_min_flow_bypass() -> ReferenceCase:
    """C9: a pump's minimum-flow bypass through a restriction orifice back to its suction
    reservoir (``solve_bypass``); the pump runs (curve_a, inside its points), NPSH not checked
    (liquid A has no vapor pressure)."""
    name = "orifice_min_flow_bypass"
    project = bypass_project(_pid(name), "Restriction orifice in a minimum-flow bypass")
    rho, mu, p_vap = dv.fluid_state(project.fluid)
    nu = mu / rho
    sol = solve_bypass(project)
    curve = curve_a()
    require_regimes(
        nu,
        [
            (sol.q_pump, BYPASS_SUCTION),
            (sol.q_pump, BYPASS_DISCHARGE),
            (sol.q_process, BYPASS_PROCESS),
            (sol.q_bypass, BYPASS_TO_RO),
            (sol.q_bypass, BYPASS_FROM_RO),
        ],
        "turbulent",
    )
    if not el.pump_in_curve_range(curve, 1.0, sol.q_pump):
        raise ValueError("the pump stays inside its curve points")
    ro = next(c for c in project.components if isinstance(c, Orifice))
    at = Ports(
        sol.q_bypass,
        sol.h_t1 - BYPASS_TO_RO.head_loss(sol.q_bypass, nu),
        BYPASS_H1 + BYPASS_FROM_RO.head_loss(sol.q_bypass, nu),
        BYPASS_TO_RO.d,
        BYPASS_FROM_RO.d,
    )
    h_s = BYPASS_H1 - BYPASS_SUCTION.head_loss(sol.q_pump, nu)
    h_d = sol.h_t1 + BYPASS_DISCHARGE.head_loss(sol.q_pump, nu)
    head = el.pump_head(curve, 1.0, sol.q_pump)
    if abs(h_d - h_s - head) > 1.0e-9:
        raise RuntimeError("the pump does not close")
    pressures = port_pressures(ro, at, rho)
    pressures["PU1:suction"] = dv.static_pressure(
        rho, h_s, 0.5, BYPASS_SUCTION.velocity(sol.q_pump)
    )
    pressures["PU1:discharge"] = dv.static_pressure(
        rho, h_d, 0.5, BYPASS_DISCHARGE.velocity(sol.q_pump)
    )
    for port, v in (
        ("run_inlet", BYPASS_DISCHARGE.velocity(sol.q_pump)),
        ("run_outlet", BYPASS_PROCESS.velocity(sol.q_process)),
        ("branch", BYPASS_TO_RO.velocity(sol.q_bypass)),
    ):
        pressures[f"T1:{port}"] = dv.static_pressure(rho, sol.h_t1, 1.0, v)
    p_atm = dv.standard_atmosphere_pressure(0.0)
    require_above_vapor_pressure(pressures, rho, p_vap, p_atm)
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={
            "L1": sol.q_pump,
            "L2": sol.q_pump,
            "L3": sol.q_process,
            "LB1": sol.q_bypass,
            "LB2": sol.q_bypass,
        },
        egl={
            "R1:port_1": BYPASS_H1,
            "R1:port_2": BYPASS_H1,
            "PU1:suction": h_s,
            "PU1:discharge": h_d,
            **{f"T1:{p}": sol.h_t1 for p in TEE_PORTS},
            "RO:inlet": at.egl_in,
            "RO:outlet": at.egl_out,
            "R2:port_1": BYPASS_H2,
        },
        pressures=pressures,
        flags=[
            {"code": "NPSH_NOT_CHECKED", "componentId": "PU1"},
            *orifice_flags(ro, at, rho, mu, p_vap, p_atm),
        ],
        pumps={"PU1": {"status": "running", "operatingFlow": sol.q_pump, "operatingHead": head}},
        orifices={"RO": orifice_expected(ro, at, rho, mu)},
    )
    return ReferenceCase(
        name=name,
        description=(
            "A pump feeding a process line, with a minimum-flow bypass through a restriction "
            "orifice back to its suction reservoir: verifies the pump's operating point with "
            "the bypass, the split between the process and the bypass, and the plate's loss "
            "at a high head."
        ),
        source=_source(
            name,
            LAW + "; pump curve PCHIP; Darcy-Weisbach + Colebrook; brentq on T1's EGL (pump "
            "side against process + bypass flows); " + STATIC,
        ),
        project=project,
        expected=expected,
    )


# --- C10: flashing at the vena contracta --------------------------------------------------------

FLASH_LINES = (Line(0.0525, 5.0), Line(0.0525, 5.0))
FLASH_BORE = 0.013125
"""m: β 0.25 on 52.5 mm, no taps (test input)."""
FLASH_SURFACE = 1.8e6
"""Pa gauge: R1's surface pressure (test input)."""
FLASH_WATER = 293.15
"""K: built-in water at 20 °C."""


def orifice_vena_contracta_flashing() -> ReferenceCase:
    """C10: built-in water at 20 °C from R1 (z 0, level 2 m, surface 1.8 MPa g) through
    52.5 mm × 5 m → RO (β 0.25, no taps) → 52.5 mm × 5 m → R2 (z 0, level 1 m): both ports far
    above the vapor pressure, but the vena contracta, p_in − (1 − β⁴)/(C_L² β⁴) ρv²/2, falls
    below it, so BELOW_VAPOR_PRESSURE (invalid) on the plate (decision 15)."""
    element = orifice("RO", 0.0, FLASH_BORE)
    case = series_case(
        name="orifice_vena_contracta_flashing",
        title="Orifice plate flashing at its vena contracta",
        description=(
            "A small restriction orifice taking most of a 1.8 MPa head in water at 20 C: "
            "verifies that its ports stay far above the vapor pressure while the vena "
            "contracta falls below it, flagged BELOW_VAPOR_PRESSURE on the plate."
        ),
        method_text=LAW + "; " + VENA + "; CoolProp water (IAPWS-95) at 293.15 K, p_v; "
        "Darcy-Weisbach + Colebrook lines; brentq; " + STATIC,
        series=Series(0.0, 2.0, 0.0, 1.0, *FLASH_LINES, element, p1=FLASH_SURFACE),
        fluid=builtin_water(FLASH_WATER),
    )
    if not any(f["code"] == "BELOW_VAPOR_PRESSURE" for f in case.expected.flags):
        raise ValueError("orifice_vena_contracta_flashing must flash")
    return case


# --- C12: an entered C at corner taps ------------------------------------------------------------

SHORT_LINES = (Line(0.1023, 1.0), Line(0.1023, 1.0))
CORNER_BORE = 0.0767
"""m: β 0.7497556 on 102.3 mm (test input)."""


def corner_series(entered: float | None = ENTERED_C) -> Series:
    """C12's network: R1 (z 0, level 1 m) → 102.3 mm × 1 m → OR1 (z 0, d 76.7 mm, corner taps,
    an entered C or ISO's) → 102.3 mm × 1 m → R2 (z 0, level 0)."""
    element = orifice("OR1", 0.0, CORNER_BORE, discharge_coefficient=entered, taps="corner")
    return Series(0.0, 1.0, 0.0, 0.0, *SHORT_LINES, element)


def orifice_entered_c_at_taps() -> ReferenceCase:
    """C12: an entered C = 0.6 at corner taps on a β 0.75 plate that dominates a short line: the
    loss uses C_L = C_e r(Re_eff), r = C_ISO(D and D/2)/C_ISO(corner) (decision 13; 0.6 as
    entered would move the flow by −2.5 %, beyond D6); the reading uses C_M = 0.6."""
    return series_case(
        name="orifice_entered_c_at_taps",
        title="Calibrated orifice meter at corner taps",
        description=(
            "A corner-tapped orifice meter of beta 0.75 with a calibrated discharge coefficient "
            "of 0.6, dominating a short line: verifies that the entered C is moved to D and D/2 "
            "tappings by ISO 5167-2's ratio of the two tap sets' coefficients for the loss, and "
            "used as entered for the reading."
        ),
        method_text=MOVED_LAW + "; " + READING + " at C_M = C_e; " + VENA + "; Darcy-Weisbach "
        "+ Colebrook lines; brentq; " + STATIC,
        series=corner_series(),
        fluid=liquid_a(),
    )


# --- C13: a moved entered C below its taps' Reynolds number ---------------------------------------

FLANGE_LOW_RE_LINES = (Line(0.3, 10.0), Line(0.3, 10.0))
FLANGE_LOW_RE_BORE = 0.21
"""m: β 0.7 on a 0.3 m line (test inputs). On D > 94 mm the flange tappings' lowest Re,
170000 β² D, lies above D and D/2's, 16000 β²: 24,990 against 7,840 here."""
FLANGE_LOW_RE_PORTS = (0.2, 0.9)
"""m: the plate's inlet and outlet port elevations, around its 0.5 m (test inputs)."""


def flange_low_re_series() -> Series:
    """C13's network: R1 (z 0, level 1.12 m) → 0.3 m × 10 m → OR1 (z 0.5 m, its inlet port at
    0.2 m and its outlet port at 0.9 m, d 0.21 m, flange taps, entered C 0.6) → 0.3 m × 10 m →
    R2 (z 0, level 1 m)."""
    inlet_z, outlet_z = FLANGE_LOW_RE_PORTS
    element = orifice(
        "OR1",
        0.5,
        FLANGE_LOW_RE_BORE,
        discharge_coefficient=ENTERED_C,
        taps="flange",
        inlet_elevation=inlet_z,
        outlet_elevation=outlet_z,
    )
    return Series(0.0, 1.12, 0.0, 1.0, *FLANGE_LOW_RE_LINES, element)


def orifice_entered_c_flange_low_re() -> ReferenceCase:
    """C13: an entered C = 0.6 at flange taps on a β 0.7 plate in a light oil (870 kg/m³,
    12 mPa·s) at Re_D ≈ 13,000, above D and D/2's Re_lo (7,840: C_L = C_e r(Re_D), not held) but
    below the flange tappings' (24,990): the move's denominator C_ISO(flange, Re_D) is eq. (4)
    below its tap set's limit, so the plate is flagged (limit reynoldsNumber; proposal §12 item
    1). The ports sit 0.7 m apart in elevation, so p_vc takes ρg(z_up − z_down) with the flow
    forward (up = the inlet port) and the static drop its ρg(z_out − z_in) term (decisions 15,
    16)."""
    name, rho, mu = LIGHT_OIL
    series = flange_low_re_series()
    case = series_case(
        name="orifice_entered_c_flange_low_re",
        title="Calibrated flange-tapped meter below its taps' Reynolds number",
        description=(
            "A flange-tapped orifice meter of beta 0.7 with a calibrated discharge coefficient "
            "of 0.6 in a light oil on a 0.3 m line, at a Reynolds number between ISO 5167-2's "
            "lowest at D and D/2 tappings and at flange tappings: verifies the move of the "
            "entered C at that Reynolds number, the Reynolds-number flag of the move, and the "
            "elevation terms of the vena contracta and static pressures with the ports at "
            "different elevations."
        ),
        method_text=MOVED_LAW + "; " + READING + " at C_M = C_e; " + VENA + " (up = the inlet "
        "port); Darcy-Weisbach + Colebrook lines; brentq; " + STATIC,
        series=series,
        fluid=custom_fluid(name, rho, mu),
    )
    law = series.law(rho, mu)
    q = case.expected.flows["L1"]
    re = law.reynolds(q)
    beta = law.beta
    flange_low = el.orifice_re_lo("flange", beta, law.d_pipe)
    if not law.re_lo_loss * (1.0 + FLOW_CLEARANCE) < re < flange_low * (1.0 - FLOW_CLEARANCE):
        raise ValueError("C13's Re_D must lie between the two tap sets' lowest Reynolds numbers")
    return case


# --- C14: reverse flow with the ports at different elevations -----------------------------------

REVERSE_PORTS = (2.4, 3.7)
"""m: C14's inlet and outlet port elevations, around OR1's 3 m (test inputs)."""


def orifice_reverse_flow_port_elevations() -> ReferenceCase:
    """C14: C4 (C1 with the heads swapped) with OR1's inlet port at 2.4 m and its outlet port at
    3.7 m: the flow enters by the outlet port, so p_vc = p_out + ρg(z_out − z_in) − (1 − β⁴)/
    (C_L² β⁴) ρv²/2 at the inlet port's elevation (decision 15, WANDA's downstream side), and
    the static drop holds ρg(z_out − z_in) (§3.7); the EGLs and the flow are C4's (D7)."""
    inlet_z, outlet_z = REVERSE_PORTS
    element = orifice(
        "OR1",
        LINE_Z,
        LINE_BORE,
        taps="flange",
        inlet_elevation=inlet_z,
        outlet_elevation=outlet_z,
    )
    return series_case(
        name="orifice_reverse_flow_port_elevations",
        title="Orifice plate in reverse flow, ports at different elevations",
        description=(
            "The reverse-flow orifice line with the plate's outlet port 1.3 m above its inlet "
            "port: verifies that the vena contracta pressure is taken from the port the flow "
            "enters to the elevation of the port it leaves by, and the elevation term of the "
            "static pressure drop."
        ),
        method_text=LAW + " (odd in Q); " + READING + "; " + VENA + " (up = the outlet port, "
        "down = the inlet port); Darcy-Weisbach + Colebrook lines; brentq; " + STATIC,
        series=line_series(element, reverse=True),
        fluid=liquid_a(),
    )


# --- EPANET networks (generate_epanet_cases, proposal §7.2) --------------------------------------

LOW_RE_LINES = (Line(0.0525, 10.0), Line(0.0525, 10.0))
LOW_RE_BORE = 0.01575
"""E3: β 0.3 on 52.5 mm, no taps (test input)."""


def low_re_epanet_project(pid: str, title: str) -> Project:
    """E3: R1 (z 0, level 1.2 m) → 52.5 mm × 10 m → OR1 (z 0, β 0.3) → 52.5 mm × 10 m → R2 (z 0,
    level 0), EPANET water, Swamee–Jain: Re_D ≈ 14,000, where eq. (4)'s Re terms matter."""
    element = orifice("OR1", 0.0, LOW_RE_BORE)
    series = Series(0.0, 1.2, 0.0, 0.0, *LOW_RE_LINES, element)
    return series.project(pid, title, epanet_water(), "swamee_jain")


def held_c_flow(series: Series, fluid: CustomFluid, re_held: float) -> float:
    """The series flow with C_L frozen at its value at Re_D = re_held (ISO's C, D and D/2), for
    the checks that a wrong Re dependence misses the reference beyond D6 (proposal §3.1)."""
    rho, mu, _ = dv.fluid_state(fluid)
    nu = mu / rho
    e = series.element
    d_pipe = series.inlet.d
    k = el.orifice_k(
        d_pipe, e.bore_diameter, el.orifice_c(d_pipe, e.bore_diameter, re_held, "d_and_d_2")
    )
    return signed_flow(
        lambda q: (
            series.inlet.head_loss(q, nu)
            + dv.minor_head_loss(q, k, d_pipe)
            + series.outlet.head_loss(q, nu)
        ),
        series.h1(rho) - series.h2,
    )


CASES: tuple[Callable[[], ReferenceCase], ...] = (
    orifice_line,
    orifice_meter_readback,
    orifice_entered_c,
    orifice_reverse_flow,
    orifice_outside_iso_geometry,
    orifice_low_reynolds,
    orifice_reynolds_dependence,
    orifice_balancing_loop,
    orifice_min_flow_bypass,
    orifice_vena_contracta_flashing,
    orifice_outlet_bore_differs,
    orifice_entered_c_at_taps,
    orifice_entered_c_flange_low_re,
    orifice_reverse_flow_port_elevations,
)
"""Proposal §7.1's table, C1-C12, and C13-C14 (added in review: the Reynolds flag of a move
from flange taps, proposal §12 item 1, and unequal port elevations in reverse flow)."""


def with_taps(series: Series, taps: OrificeTaps | None) -> Series:
    """The same series with the plate's taps changed (a meter's taps change no solved value on
    ISO's C, decision 5)."""
    return replace(series, element=series.element.model_copy(update={"taps": taps}))
