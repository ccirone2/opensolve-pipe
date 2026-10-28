"""Methods and assumptions of a solve (design §13, GOALS §4.2): ``MethodsSummary``.

One summary per solve, written to be pasted into a deliverable: sections for the network
solution, friction, minor losses, branches, pumps, valves, relief valves, equipment and orifice
plates (each of the last three only in a project that has some), fluid properties, atmosphere and NPSH, and conventions; the global
assumptions; and the software versions, with the calculation-method version. Every number in it
is a constant the solver uses or a value of this solve.
"""

import CoolProp
import fluids
import numpy as np
import scipy

from ... import __version__
from ...models.components import AssignedFlow
from ...models.piping import ENTRANCE_TYPES, EXIT_TYPES
from ...models.results import MethodsSection, MethodsSummary
from .branches import DARBY_TEE
from .builder import BuiltNetwork
from .friction import (
    COLEBROOK_ED_DOCUMENTED_MAX,
    COLEBROOK_ED_LIMIT,
    RE_LAMINAR_MAX,
    RE_TURBULENT_MIN,
    SWAMEE_JAIN_ED_RANGE,
    SWAMEE_JAIN_RE_RANGE,
)
from .gga import (
    CONTINUITY_ATOL,
    CONTINUITY_RTOL,
    ENERGY_ROUNDOFF,
    ENERGY_TOL,
    JACOBIAN_FLOOR_RELATIVE,
    ZERO_FLOW_RTOL,
)
from .orifice import (
    BETA_RANGE,
    BORE_MIN,
    ISO_5167_2,
    PIPE_RANGE,
    RE_LO_BETA,
    RE_LO_FLANGE,
    RE_LO_MIN,
    READER_HARRIS_2019,
    WANDA,
)
from .relief import (
    AFT,
    API_520,
    API_526,
    API_CONSTANT,
    ASME_DEFAULT_WORDS,
    ASME_SCOPE_WORDS,
    CONSTANT_EXCESS,
    DECISION,
    EXACT_CONSTANT,
    PENTAIR,
    SIMSCAPE,
    VISCOSITY_LIMIT,
)
from .status import HTOL, K_TOL, MAX_OUTER_ITERATIONS, OFFSET_TOL, QTOL, OuterLoopResult
from .system_curve import DEFAULT_RANGE_FACTOR
from .valves import IDEAL_CONTROL_VALVE
from .version import METHOD_VERSION

TODINI_PILATI = (
    "Todini, E., and S. Pilati. A gradient algorithm for the analysis of pipe networks. "
    "Computer Applications in Water Supply, Vol. 1. Wiley, 1988, 1-20."
)
COLEBROOK = "Colebrook, C. F. J. ICE 11(4), 1939, 133-156, doi:10.1680/ijoti.1939.13150."
CLAMOND = "Clamond, D. Ind. Eng. Chem. Res. 48(7), 2009, 3665-3671, doi:10.1021/ie801626g."
SWAMEE_JAIN = "Swamee, P. K., and A. K. Jain. J. Hydraulics Div. ASCE 102(5), 1976, 657-664."
EPANET = "Rossman, L. A., et al. EPANET 2.2 User Manual. US EPA, 2020 (source: src/hydcoeffs.c)."
EPANET_STATUS = (
    "Rossman, L. A., et al. EPANET 2.2. US EPA, 2020 (source: src/hydstatus.c, status rules)."
)
CRANE = "Crane Co. TP-410 Flow of Fluids Through Valves, Fittings, and Pipe, 2009."
RENNELS = (
    "Rennels, D. C., and H. M. Hudson. Pipe Flow: A Practical and Comprehensive Guide. Wiley, 2012."
)
DARBY = (
    "Silverberg, P., and R. Darby. Correlate pressure drops through fittings. Chem. Eng. "
    "106(7), 1999, 101."
)
FORD_FULKERSON = (
    "Ford, L. R., and D. R. Fulkerson. Maximal flow through a network. Canadian Journal of "
    "Mathematics 8, 1956, 399-404 (the max-flow min-cut theorem: the flows no state carries "
    "through a pump on its system curve)."
)
FRITSCH_CARLSON = (
    "Fritsch, F. N., and R. E. Carlson. Monotone piecewise cubic interpolation. SIAM J. Numer. "
    "Anal. 17(2), 1980, 238-246."
)
FRITSCH_BUTLAND = (
    "Fritsch, F. N., and J. Butland. A method for constructing local monotone piecewise cubic "
    "interpolants. SIAM J. Sci. Stat. Comput. 5(2), 1984, 300-304, doi:10.1137/0905021 (the "
    "derivative formula of scipy.interpolate.PchipInterpolator)."
)
ISA_75 = "ISA-75.01.01-2007 (60534-2-1 Mod), Flow Equations for Sizing Control Valves."
USSA_1976 = "U.S. Standard Atmosphere, 1976. NOAA, NASA, USAF, Washington, DC, 1976."
BRENT = (
    "Brent, R. P. Algorithms for Minimization without Derivatives. Prentice-Hall, 1973, ch. 4 "
    "(scipy.optimize.brentq)."
)
EPANET_SPECIFIC_FLOW = (
    "Rossman, L. A., et al. EPANET 2.2 User Manual, ch. 13 (Frequently Asked Questions, "
    '"How do I size a pump to meet a specific flow?": the pump closed, a demand equal to the '
    "flow at its suction node and a negative demand at its discharge node). US EPA, 2020. "
    "https://usepa.github.io/EPANET2.2/13_questions.html"
)
FIXED_SPEED_OVERRIDE = (
    'Bentley WaterGEMS CONNECT Edition Help, "VSP Interactions with Simple and Logical '
    'Controls": in Fixed Speed Override a variable-speed pump operates at its maximum speed '
    "setting and the target is no longer maintained. https://docs.bentley.com/LiveContent/web/"
    "Bentley%20WaterGEMS%20SS6-v1/en/GUID-31A4A446A15F448E8C7BD7C3B8D1249E.html"
)
EPANET_SPEED_EFFICIENCY = (
    "Rossman, L. A., et al. EPANET 2.2. US EPA, 2020 (source: src/hydraul.c:983-984, the Sarbu "
    "and Borza pump speed adjustment of efficiency, not applied here)."
)
SPEED_CONTROL_DECISION = (
    "OpenSolve Pipe design decision D11 (CLAUDE.md), from docs/proposals/vfd-pump-modes.md."
)
GALE = (
    "Gale, D. A theorem on flows in networks. Pacific Journal of Mathematics 7(2), 1957, "
    "1073-1082 (a flow with fixed supplies and demands exists when no node set holds more net "
    "supply than its cut can pass: the assigned flows in a pump's system-curve bounds)."
)


def _energy_roundoff_sentence() -> str:
    """The energy stop test's round-off allowance (gga.ENERGY_ROUNDOFF, method 1.2.0), stated
    after the tolerance it is added to. The bound is the quotient itself: its printed value is
    rounded (up, at 6 digits), so the sentence gives it as "about"."""
    eps = float(np.finfo(np.float64).eps)
    return (
        f"On each link, {ENERGY_ROUNDOFF:g} x the largest magnitude among the energy grade "
        "lines at its two ends and its head loss is added to that tolerance "
        f"({ENERGY_ROUNDOFF / eps:g} x {eps:g}, the machine epsilon of double precision): an "
        "allowance for the round-off of the heads that the energy residual subtracts, larger "
        f"than {ENERGY_TOL:g} m only where that magnitude exceeds {ENERGY_TOL:g} m divided by "
        f"that factor, about {ENERGY_TOL / ENERGY_ROUNDOFF:g} m."
    )


EQUIPMENT_ASSUMPTION = (
    "Equipment losses scale with the square of the flow and with density from one rated point, "
    "a Cv or a Kv (constant K); viscosity is not corrected."
)
"""The assumption a project with equipment adds (proposal equipment-pressure-drop.md §4.2)."""


def equipment_section(built: BuiltNetwork) -> MethodsSection | None:
    """The "Equipment" section, only for a project with equipment (proposal
    equipment-pressure-drop.md §4.2); its Cv/Kv item only when an element is rated by one."""
    if not built.equipment:
        return None
    coefficients = any(d.law.kind != "point" for d in built.equipment.values())
    items = [
        "Equipment (one side of a heat exchanger, a coil, a strainer, a filter, or another "
        "passive element given by its datasheet): the loss of total head from its inlet to its "
        "outlet is h = EGL_in − EGL_out = c Q|Q| (a loss of total pressure ρ g h), with c = "
        "ΔP_r/(ρ_r g Q_r²) from the rated pressure drop ΔP_r at the rated flow Q_r for a fluid "
        "of density ρ_r: a constant K, the square law of ISA-75.01.01-2007 eq. (1) for "
        "non-choked, turbulent liquid flow, and the high-Re limit of the 3-K method (Silverberg "
        "& Darby). The rated drop is the dissipative "
        "loss (friction and form) of total pressure between the ports, without the static head "
        "between them: each port's static pressure follows from its EGL with the velocity in "
        "its connected pipe, so the static drop reported is ρ g h + ρ g (z_out − z_in) + "
        "ρ (v_out² − v_in²)/2.",
        "Density scaling: the pressure loss at the solved flow is ρ g h = ΔP_r (ρ/ρ_r)(Q/Q_r)², "
        "with ρ the fluid being solved. The operating density cancels out of the head loss h, "
        "which the rating alone sets; it only converts head to pressure.",
    ]
    if coefficients:
        items.append(
            "A Cv or Kv rating is a rated point on water by definition (1 psi at Cv US gpm, 1 "
            "bar at Kv m³/h): c = K/(2 g A²) with K from fluids.fittings.Cv_to_K / Kv_to_K "
            "(ISA-75.01.01-2007, water at 999.29744568 kg/m³), the valves' conversion, evaluated "
            "at a 1 m bore; K ∝ D⁴ makes K/A² the same on every bore, so no pipe diameter is "
            "needed. Its pressure loss is (ρ/ρ_w) × 1 psi × (Q/Cv gpm)², or × 1 bar × (Q/Kv "
            "m³/h)²."
        )
    items += [
        "Reverse flow (outlet → inlet) follows the same, symmetric law and is flagged: no "
        "datasheet rates reverse flow.",
        f"Laminar flow (Re < {RE_LAMINAR_MAX:g}) in the end segment of a connected pipe is "
        "flagged, as for a valve's Cv or Kv: the square law is the turbulent-flow law, and the "
        "loss is then likely underestimated.",
        "At zero flow the law's slope 2c|Q| is 0: Newton's Jacobian uses at least "
        f"{JACOBIAN_FLOOR_RELATIVE:g} x the slopes of the pipes at the element's ports there, as "
        "for every link that is not a pipe (EPANET 2.2 bounds such a gradient instead); the law "
        "itself is exact.",
        "Viscosity is not corrected: the loss scales with density only. With a fluid more "
        "viscous than the rating's, or at flows well below the rated flow, the real loss may be "
        "higher than this law gives (a smooth-tube element dominated by friction scales as "
        "ρ^0.75 μ^0.25 Q^1.75 by Blasius' law); a correction needs the equipment's geometry or "
        "its vendor's own factors.",
    ]
    return MethodsSection(title="Equipment", items=items, references=[ISA_75, DARBY])


ORIFICE_ASSUMPTION = (
    "Orifice plates meet ISO 5167-2 in geometry and installation; their loss is ISO 5167-2's "
    "permanent pressure loss with the discharge coefficient at D and D/2 tappings (or an entered "
    "one), for a single-phase liquid."
)
"""The assumption a project with orifice plates adds (proposal orifice-plate.md §4.2)."""


def orifice_section(built: BuiltNetwork) -> MethodsSection | None:
    """The "Orifices" section, only for a project with orifice plates (proposal orifice-plate.md
    §4.2); its entered-coefficient items only when a plate has one."""
    if not built.orifices:
        return None
    entered = any(d.law.entered is not None for d in built.orifices.values())
    beta_low, beta_high = BETA_RANGE
    pipe_low, pipe_high = PIPE_RANGE
    items = [
        "Orifice plates (square-edged, concentric; a restriction orifice, or a flow meter with "
        "pressure taps): the loss of total head from the inlet to the outlet is h = EGL_in − "
        "EGL_out = K v|v|/(2g), with v = Q/A in the inlet pipe of inner diameter D (its end "
        "segment at the inlet port), β = d/D, and K = (S/(C β²) − 1)², S = √(1 − β⁴(1 − C²)): ISO "
        "5167-2's pressure-loss relation Δϖ = (S − C β²)/(S + C β²) × Δp over ρ v²/2 "
        "(fluids.flow_meter.discharge_coefficient_to_K, computed without its cancellation as "
        "β → 1). Δϖ = ρ g h is the permanent pressure loss, the part not recovered about 6 D "
        "downstream; the outlet port's pressure is the recovered one.",
        "The discharge coefficient C that sets the loss is the one at D and D/2 tappings for every "
        "plate, whatever its own taps: ISO 5167-2:2003 eq. (4), the Reader-Harris/Gallagher "
        "equation (fluids.flow_meter.C_Reader_Harris_Gallagher), at Re_D = 4ρ|Q|/(πDμ) in the "
        "inlet pipe. One plate has one permanent loss; the loss relation's theory (Reader-Harris "
        "et al. 2019) takes C with tappings 1D upstream, and of ISO's tap sets only D and D/2 "
        "has L1 = 1 (Deltares WANDA makes the same choice). Named departures, each at its largest "
        "over ISO 5167-2's range (D 50 mm to 1 m, β 0.1 to 0.75, Re_D from Re_lo up): ISO's "
        "relation read with a meter's own C would give a K up to 6.14 % higher at corner "
        "tappings and 6.34 % at flange tappings (at β 0.75 as Re_D grows, flange on a 1 m pipe), "
        "a flow up to 2.94 % and 3.03 % lower where the plate takes the whole head (up to β 0.6: "
        "a K up to 0.64 % and 0.84 % higher, a flow up to 0.32 % and 0.42 % lower); Reader-Harris "
        "et al.'s own C, with the downstream pressure at 0.125 D, gives a K 0.063 to 1.24 % lower "
        "(a flow up to 0.63 % higher).",
        f"Below ISO 5167-2's lowest Reynolds number Re_lo, C is held at its value there and "
        f"flagged (WANDA's practice; eq. (4) as written exceeds 1 at very low Re): Re_lo = "
        f"max({RE_LO_MIN:g}, {RE_LO_BETA:g} β²) at corner and D and D/2 tappings and "
        f"max({RE_LO_MIN:g}, {RE_LO_FLANGE:g} β² D) at flange tappings (D in m). The first is "
        "ISO's limit (5000 for β ≤ 0.56, 16000 β² above) made continuous at β 0.56, stricter by "
        "at most 17.6 for 0.559 < β < 0.56, so that the held loss decreases with β. So fluids is "
        "never evaluated below Re 5000, where it adds terms that are not in ISO 5167-2.",
        "A plate whose coefficient that sets the loss, at D and D/2 tappings (ISO's C there, or an "
        "entered C moved there from corner or flange taps), could exceed 1 at some flow is "
        "refused (ORIFICE_OUT_OF_RANGE): C ≤ 1 is a jet no larger than the bore, and above it K "
        "falls below the sudden expansion from the bore (Borda-Carnot), which is physically "
        "impossible. So is a plate whose ISO coefficient could exceed 1 where eq. (4) serves only "
        "the reading or the move: at its corner or flange tappings for ISO's meter reading, or at "
        "either tap set in the ratio that moves an entered C. Eq. (4) is then extrapolated far "
        "beyond ISO's range (its largest C there is below 0.7), and the reading or the move would "
        "rest on it. Each bound takes each Reynolds-number-dependent term of eq. (4) at whichever "
        "end of [Re_lo, ∞) makes it safe. For ISO's C it refuses β from about 0.970 (0.97025 "
        "from D 71.12 mm, at most 0.9706 on smaller pipes), and with flange taps on a pipe below "
        "about 55 mm, where ISO's C at the flange tappings is the bound, from a lower β (0.969 at "
        "D 52.5 mm, 0.963 at 40.9 mm, 0.930 at 15.8 mm, lower still on smaller pipes). A plate "
        "whose loss coefficient K/(2 g A²) at its smallest C is not a finite positive "
        "floating-point number is refused too.",
        "A meter's reading, the differential pressure between its taps, is ISO 5167-2 eq. (1) "
        "solved for Δp with ε = 1: Δp = (1 − β⁴)/(C_M² β⁴) · ρ v|v|/2, with C_M ISO's C at its "
        "own taps (held at their own Re_lo) or the entered C; it does not act on the network. A "
        "plate without taps (a restriction orifice) has no reading.",
        "The static pressure at the vena contracta, p_vc = p_up + ρ g (z_up − z_down) − "
        "(1 − β⁴)/(C² β⁴) · ρ v²/2 (up: the port the flow enters; down: the port it leaves by, at "
        "whose elevation it is taken, as in WANDA), is checked against the vapor pressure and "
        "flagged where the liquid would flash (BELOW_VAPOR_PRESSURE): a flashing jet chokes the "
        "flow, so the flow solved is then too high. None at zero flow or where the pressure "
        "level is undetermined; incipient cavitation is not checked.",
        f"Flagged (CORRELATION_OUT_OF_RANGE), wherever eq. (4) is used: a bore below "
        f"{BORE_MIN * 1000:g} mm, an inlet pipe outside {pipe_low * 1000:g} mm to "
        f"{pipe_high * 1000:g} mm, β outside {beta_low:g} to {beta_high:g} (ISO 5167-2's limits, "
        "from fluids' documentation); and for every plate, an outlet pipe of another bore than "
        "the inlet's (the relation assumes the jet recovers in the same bore) and reverse flow "
        "(the loss taken as for forward flow at the same flow rate: ISO's C is for flow onto the "
        "plate's upstream face). The plate and its installation (edge, thickness, straight "
        "lengths, roughness) are assumed to meet ISO 5167-2 and are not checked.",
        "At zero flow the law's slope is 0: Newton's Jacobian uses at least "
        f"{JACOBIAN_FLOOR_RELATIVE:g} x the slopes of the pipes at the plate's ports there, as "
        "for every link that is not a pipe; the law itself is exact. Elsewhere the slope is exact, "
        "with the derivative of eq. (4) in the Reynolds number.",
        "ε = 1: the expansibility factor of a liquid.",
    ]
    if entered:
        items += [
            "An entered discharge coefficient is ISO 5167-2 eq. (1)'s C at the plate's taps (at D "
            "and D/2 tappings for a plate without taps), from a calibration or datasheet, held at "
            "every flow; it is not the flow coefficient α = C/√(1 − β⁴). The reading uses it as "
            "entered. The loss uses it as entered without taps or at D and D/2 tappings, and from "
            "corner or flange tappings moved to D and D/2 tappings by ISO's ratio of the two tap "
            "sets' C at the same Reynolds number, r = C_ISO(D and D/2)/C_ISO(taps) (held below "
            "Re_lo), so that one plate has one loss and a calibration equal to ISO's C gives "
            "ISO's answer.",
            f"Laminar flow (Re_D < {RE_LAMINAR_MAX:g}) in the inlet pipe of a plate with an "
            "entered coefficient is flagged, as for a valve's Cv or Kv: a held C is the square law "
            "of turbulent flow, and the loss is then likely underestimated.",
        ]
    return MethodsSection(
        title="Orifices", items=items, references=[ISO_5167_2, READER_HARRIS_2019, WANDA, RENNELS]
    )


RELIEF_ASSUMPTION = (
    "Relief valves are conventional spring-loaded valves in liquid service, lifting linearly (a "
    "convention) from their set pressure difference to full lift at set plus overpressure, with "
    "API 520's liquid capacity equation on the total-pressure difference across them."
)
"""The assumption a project with relief valves adds (proposal pressure-relief-valve.md §4.2)."""


def relief_section(built: BuiltNetwork) -> MethodsSection | None:
    """The "Relief valves" section, only for a project with a relief valve (proposal
    pressure-relief-valve.md §4.2)."""
    if not any(d.relief is not None for d in built.valves.values()):
        return None
    items = [
        "Pressure relief valves (conventional spring-loaded, liquid service): the lift x rises "
        "linearly from 0 at the set pressure difference Δp_s to 1 at full lift, Δp_f = Δp_s (1 + "
        "op), and the flow is API 520's liquid capacity equation at that lift, Q = x Kd A √(2 Δp_t"
        "/ρ), in exact SI with Kw = Kc = Kv = 1 (API 520's own form rounds its constant to "
        f"{API_CONSTANT:g}, {CONSTANT_EXCESS:.6g} above the exact {EXACT_CONSTANT:.12g}, which "
        "gives that fraction more area for a flow). Δp_t is the total-pressure difference between "
        "the ports, (p_in + ρ v_in²/2) − (p_out + ρ v_out²/2) = ρ g (EGL_in − EGL_out − (z_in − "
        "z_out)); on the energy grade line the law is h(Q) = h_set + (Δp(Q) − Δp_s)/(ρ g), h_set "
        "= Δp_s/(ρ g) + z_in − z_out, with u = √Δp the largest real root of u³ − Δp_s u − R Q = 0 "
        "between set and full lift (R = (Δp_f − Δp_s)/(Kd A √(2/ρ)); the increment R Q/u and its "
        "slope computed without cancellation) and Δp = ρ Q²/(2 (Kd A)²) from full lift on. h is "
        "continuous and strictly increasing, with a finite positive slope at zero flow.",
        "Three named departures. (1) The band between set and full lift is a convention, the "
        "linear lift of MathWorks Simscape and AFT Impulse, exact at the two points the "
        "certification fixes, not the cited behaviour: Pentair's typical liquid-trim "
        "characteristic (TP-V300 Fig. 4-12) lifts to about half at 107 % of set, surges to full "
        "lift there, and on falling pressure stays at full lift to about 95 % and recloses near "
        "90 %, so between about 90 % and 107 % of set a real valve has two steady states; a "
        "valve that has surged open passes more flow at a lower inlet pressure. No cited source "
        "verifies a band law, so every relieving state short of full lift is flagged "
        "(CORRELATION_OUT_OF_RANGE, partial lift), and the band is an exception to the project's "
        "verifiable gate that the owner accepted (CLAUDE.md D21). (2) API 520's P1 − P2 is read "
        "as Δp_t; ASME's definitions as Pentair quotes them (the inlet stagnation pressure, the "
        "outlet static pressure) differ by the outlet velocity head, and this reading gives the "
        "higher inlet pressure at a given flow. (3) With a superimposed back pressure the "
        "overpressure is taken on the set difference, as the opening is, so full lift comes op × "
        "the back pressure below the in-situ relieving pressure; at the relieving pressure both "
        "readings are at or past full lift and give API 520's flow.",
        f"Overpressure at full lift: {ASME_DEFAULT_WORDS} (the default), ASME VIII's liquid "
        f"certification overpressure, for a set of at least {ASME_SCOPE_WORDS}, ASME VIII's "
        "scope; a certified capacity may give its own. Below that scope the default is not "
        "cited: a valve that would take it is refused (RELIEF_VALVE_OUT_OF_RANGE), with the "
        "remedy of a certified capacity and its overpressure.",
        "Capacity, one of three kinds, never mixed: an API 526 orifice letter (its effective "
        "area) or an API 520 effective area, each with API 520's effective coefficient of "
        "discharge 0.65 and ASME's overpressure, for preliminary sizing (an effective area is "
        "reported with the smallest API 526 letter covering it, fluids.safety_valve."
        "API520_round_size); or the valve's certified actual orifice area with its rated "
        "coefficient of discharge (ASME's K, 0.9 × the measured coefficient) and, optionally, "
        "its full-lift overpressure. Pentair: never an effective coefficient or area with a "
        "rated coefficient or actual area.",
        "Status: active, or locked closed (gagged, or isolated by its block valve). Its status "
        "rule is the check valve's (EPANET 2.2 cvstatus) with the cracking head h_set: at zero "
        f"flow it opens once the static pressure difference across it exceeds its set by ρ g × "
        f"{HTOL:g} m, and it closes on reverse flow. It starts closed, its normal state (a pump "
        "deadheaded behind a valve set above its shutoff then runs at zero flow with its shutoff "
        "pressure on the inlet). A check valve's cracking pressure, unlike the relief valve's "
        "set, is compared with the difference of the energy grade lines. Every closed-off, "
        "free-level and system-curve rule applies to it as to a check valve (in a pump's system "
        "curve it passes no reverse flow).",
        "Flagged: full lift (RELIEF_VALVE_OPEN, information); relieving short of full lift "
        "(CORRELATION_OUT_OF_RANGE, partial lift, warning); an active valve closed with a side "
        "closed off or on an undetermined level, which has no result (RELIEF_VALVE_CLOSED, "
        "information, naming the levels that keep it closed); an outlet whose absolute static "
        "pressure is below the vapor pressure while it relieves (BELOW_VAPOR_PRESSURE: the jet "
        "would flash, and the flow solved is too high); a liquid of viscosity "
        f"{VISCOSITY_LIMIT:g} Pa·s or more (CORRELATION_OUT_OF_RANGE, viscosity: API 520's Kv, "
        "given in the trace, is not applied). Refused (RELIEF_VALVE_OUT_OF_RANGE): a law the "
        "floating point cannot represent (Kd A, Q_f or R not a finite positive normal number), "
        "and a set below ASME VIII's scope with ASME's default overpressure.",
        "Not applied: API 520's back-pressure correction Kw (a conventional valve's set is the "
        "difference across it), its rupture-disc combination factor Kc and its viscosity "
        "correction Kv; no blowdown or pop action; the outlet piping is liquid-full.",
    ]
    return MethodsSection(
        title="Relief valves",
        items=items,
        references=[API_520, API_526, PENTAIR, SIMSCAPE, AFT, EPANET_STATUS, DECISION],
    )


def libraries() -> dict[str, str]:
    """Versions of the software that produced the results."""
    return {
        "opensolve-pipe": __version__,
        "fluids": fluids.__version__,
        "CoolProp": CoolProp.__version__,
        "numpy": np.__version__,
        "scipy": scipy.__version__,
    }


def methods_summary(
    built: BuiltNetwork, p_atm_source: str, outer: OuterLoopResult | None = None
) -> MethodsSummary:
    """The methods summary of one solve (module docstring)."""
    method = built.friction_method
    turbulent = (
        "the Colebrook (1939) equation, solved exactly with fluids.friction.Clamond (Clamond 2009)"
        if method == "colebrook"
        else "the Swamee & Jain (1976) explicit approximation, f = 1/[-2 log10(ε/(3.7 D) + "
        "5.74/Re^0.9)]², in EPANET 2.2's form (hydcoeffs.c), for like-for-like EPANET "
        "comparisons"
    )
    fluid = built.fluid
    project = built.project
    settings = project.settings.solver_options if project is not None else None
    iteration_items: list[str] = []
    if settings is not None:
        iteration_items.append(
            f"This project: friction method '{settings.friction_method}', flow tolerance "
            f"{settings.tolerance:g} (relative to the largest flow), at most "
            f"{settings.max_iterations} Newton iterations per network solve."
        )
    controlled = any(pump.control is not None for pump in built.pumps.values())
    speed_control_items: list[str] = []
    speed_control_references: list[str] = []
    system_curve_control = ""
    if controlled:
        speed_control_items = [
            "Speed-controlled pumps (flow setpoint): F(s, Q) = s² H₀(Q/s) is the pump's head at "
            "speed s, between its minimum speed s_min and its speed s_max (the maximum). F rises "
            "with speed on [s_lo, s_max], s_lo = max(s_min, Q/x_mono), where 2 H₀ − (Q/s) H₀' > "
            "0 (checked exactly on the curve's cubic pieces, a curve that fails being rejected; "
            "x_mono follows from the curve's end tangent, and a setpoint of s_max x_mono or "
            "more, where F falls with speed at every speed up to s_max so that no speed holds "
            "it, is rejected too). While a speed in [s_lo, s_max] holds "
            f"the setpoint, F(s_lo, Q_set) − {HTOL:g} m ≤ EGL_d − EGL_s ≤ F(s_max, Q_set) + "
            f"{HTOL:g} m (the status head tolerance), the pump carries the setpoint as a fixed "
            "flow (EPANET 2.2's substitute for a pump of a specific flow) and its speed is the "
            "unique root of F(s, Q_set) = EGL_d − EGL_s on [s_lo, s_max] (Brent's method). "
            "This equals solving the speed with the network: it enters only the pump's own head "
            "equation. s_lo is above s_min only when Q_set/s_min lies beyond x_mono, where head "
            "falls as speed rises, a stretch no stable flow controller holds. Then, for a head "
            "at the setpoint between F(s_lo, Q_set) and F(s_min, Q_set), the pump held at s_min "
            "and passing more than the setpoint is a steady state too (a drive saturated at its "
            "minimum); the solve starts with the pump active and does not move it to s_min for "
            "a head in that band.",
            "Outside that band the pump runs as a fixed-speed pump at the nearer limit and the "
            "setpoint is not held (flagged): above it the drive saturates at maximum speed "
            "(as WaterGEMS' Fixed Speed Override), below it the pump runs at its minimum speed "
            "and passes more than the setpoint. It returns to regulating once the flow at the "
            "limit reaches the setpoint (EPANET 2.2 fcvstatus). At zero flow its controller is "
            "at maximum speed, so it closes and re-opens as a fixed-speed pump at its maximum "
            "speed (EPANET 2.2 pumpstatus).",
            "Efficiency and NPSHr at the solved speed by the affinity laws; no reduced-speed "
            "efficiency correction (EPANET 2.2 applies Sarbu and Borza's).",
            "Two flow controls in series holding the same flow (two speed-controlled pumps, or "
            "one and an FCV, with equal setpoints) leave the pressure between them undetermined: "
            "reported as not converged, naming them.",
        ]
        speed_control_references = [
            EPANET_SPECIFIC_FLOW,
            BRENT,
            FIXED_SPEED_OVERRIDE,
            EPANET_SPEED_EFFICIENCY,
            SPEED_CONTROL_DECISION,
        ]
        system_curve_control = (
            " A speed-controlled pump's own control is replaced by the fixed flow at each "
            "point; other speed-controlled pumps that are on keep regulating; its default range "
            "uses its maximum speed."
        )
    assigned = [comp for comp in built.components.values() if isinstance(comp, AssignedFlow)]
    assigned_items: list[str] = []
    assigned_references: list[str] = []
    system_curve_assigned = ""
    if assigned:
        assigned_items = [
            "Assigned-flow nodes fix the flow leaving the network at their port (a demand, "
            "positive) or entering it (a supply, negative), whatever the pressure there: a nodal "
            "demand in the continuity equations, as EPANET's junction demands; their pressure is "
            "a result. They are not a fixed-pressure boundary. A dead-end branch to one carries "
            "its flow. A part of the network that no reservoir or reference node reaches through "
            "open elements carries assigned flows only if they sum to zero (to the continuity "
            "tolerance): its flows are then solved and its pressure level is not (flagged); "
            "otherwise the closed elements around that part whose status rules open as its "
            "pressure falls (a net demand) or rises (a net supply) are re-opened; with none left "
            "to open, no steady state carries them, and the solve is reported as not converged, "
            "naming the nodes and the elements closed around them (EPANET: a disconnected "
            "system). A flow control (an FCV, or a speed-controlled pump) that alone feeds "
            "assigned-flow nodes taking its setpoint flow leaves the pressure between them "
            "undetermined (reported as not converged, naming them); with another flow the node's "
            "flow passes and the control's rules take it to a limit (an FCV fully open below its "
            "setpoint, a speed-controlled pump at its maximum or minimum speed), or, above what "
            "the control can pass, or with reverse flow through it, no steady state carries it.",
        ]
        assigned_references = [EPANET]
        system_curve_assigned = (
            " With assigned-flow nodes, the cut counts their flows as fixed demands and supplies "
            "(Gale): a demand on the pump's side of the cut takes part of the forced flow, and "
            "one beyond it adds to what the cut must pass. Read the other way, the cut bounds the "
            "flow from below: a flowing point below the least flow that assigned flows need "
            "through the pump (a demand on its discharge side that a one-way element keeps every "
            "reservoir and reference node from feeding, or a supply on its suction side that one "
            "keeps from draining) has no steady state either and is not solved again, and one at "
            "that floor is solved with each FCV of the cut held open too. A side of the pump "
            "that reaches only assigned-flow nodes has no point with a head."
        )
    reliefs = relief_section(built)
    equipment = equipment_section(built)
    orifices = orifice_section(built)
    if outer is not None:
        iteration_items.append(
            f"This solve: {outer.inner_iterations} Newton iterations in "
            f"{outer.outer_iterations} outer iteration(s); "
            + ("converged." if outer.converged else f"did not converge ({outer.message}).")
        )
    return MethodsSummary(
        method_version=METHOD_VERSION,
        sections=[
            MethodsSection(
                title="Network solution",
                items=[
                    "Global Gradient Algorithm (Todini & Pilati 1988): Newton's method on the "
                    "energy grade line at every node and the flow in every link; sparse direct "
                    "solve of the Schur complement (SciPy SuperLU, splu). One solver for every "
                    "topology; every connected part needs a reservoir or reference node.",
                    "Converged when the largest flow change is at most the project tolerance "
                    f"times the largest flow (plus {CONTINUITY_ATOL:g} m³/s), continuity closes "
                    f"at every node and over every component to {CONTINUITY_RTOL:g} x the "
                    f"largest flow + {CONTINUITY_ATOL:g} m³/s, and the energy equation holds on "
                    f"every link to {ENERGY_TOL:g} m. {_energy_roundoff_sentence()}",
                    "An active PRV or PSV holds its port's head and passes the flow of the pipe "
                    "on that port, coupled exactly in Newton's step (EPANET 2.2 lags it by one "
                    "iteration, which converges the same answer more slowly).",
                    *iteration_items,
                    "Branch components (tees, wyes) are imposed exactly: each one's ports share "
                    "one head unknown, offset by the branch's path losses (zero for an ideal "
                    "junction), and its internal flows follow from continuity.",
                    f"Flows below {ZERO_FLOW_RTOL:g} x the largest flow (plus "
                    f"{CONTINUITY_ATOL:g} m³/s) are round-off and reported as zero. Dead-end "
                    "branches (no way out but the node they hang from) carry no flow by "
                    "continuity and are reported as exactly zero.",
                    f"Outer loop for statuses and branch losses: at most {MAX_OUTER_ITERATIONS} "
                    "counted iterations; an iteration that only holds or releases branch legs at "
                    "zero flow is not counted (each branch is held a bounded number of times). "
                    "Once pump and valve statuses repeat after an iteration that changed several "
                    "of them, one status changes per iteration; a status pattern that still "
                    "repeats goes back to the latest iteration that asked for several changes "
                    "and takes one not yet taken, and with none left is reported as not "
                    "converged, naming the elements that oscillate.",
                    "Parts of the network closed off from every reservoir and reference node by "
                    "closed elements carry no flow and have no computed pressure (flagged).",
                    "A closed-off part that cannot carry zero flow (a pump loop behind a closed "
                    "valve) has determined flows but no pressure level: its flows and head "
                    "differences are solved with one node held at an arbitrary head, and its "
                    "pressures, NPSH available and PRV/PSV setpoint checks are not reported "
                    "(flagged).",
                    *assigned_items,
                ],
                references=[TODINI_PILATI, *assigned_references],
            ),
            MethodsSection(
                title="Pipe friction",
                items=[
                    f"Darcy–Weisbach head loss h = f (L/D) v²/(2g), g = {built.g:g} m/s² "
                    "(standard gravity, fluids.constants.g), Re = |v| D/ν.",
                    f"Laminar, Re < {RE_LAMINAR_MAX:g}: f = 64/Re (Hagen–Poiseuille).",
                    f"Turbulent, Re ≥ {RE_TURBULENT_MIN:g}: {turbulent}.",
                    f"Transition, {RE_LAMINAR_MAX:g} ≤ Re < {RE_TURBULENT_MIN:g}: cubic "
                    "interpolation between the laminar and turbulent laws (Dunlop's method, "
                    "as in EPANET 2.2); flagged as transitional flow.",
                    "Flagged outside the cited range: Swamee–Jain beyond its documented "
                    f"{SWAMEE_JAIN_RE_RANGE[0]:g} ≤ Re ≤ {SWAMEE_JAIN_RE_RANGE[1]:g} and "
                    f"{SWAMEE_JAIN_ED_RANGE[0]:g} ≤ ε/D ≤ {SWAMEE_JAIN_ED_RANGE[1]:g}; Colebrook "
                    f"beyond ε/D = {COLEBROOK_ED_DOCUMENTED_MAX:g}, the largest relative roughness "
                    "documented for its explicit approximations (fluids.friction.fmethods). "
                    f"ε/D ≥ {COLEBROOK_ED_LIMIT:g} has no Colebrook solution and is rejected.",
                    "Pipe dimensions: ASME B36.10M / B36.19M and ASTM D1785 via fluids.piping; "
                    "roughness: Farshad & Rieke (2006) via fluids.friction.roughness_Farshad; "
                    "user values where entered (each element's trace names its sources).",
                ],
                references=[COLEBROOK, CLAMOND, SWAMEE_JAIN, EPANET],
            ),
            MethodsSection(
                title="Minor losses",
                items=[
                    "Fitting loss h = n K v²/(2g), K from the cited fluids correlation for the "
                    "fitting type (data/fittings.json) at the reference pipe's inner diameter; "
                    "a user K overrides it.",
                    "Crane TP-410 K values use the fully turbulent friction factor ft_Crane(D); "
                    "they are not valid in laminar flow, and a Crane K in a laminar segment is "
                    "flagged.",
                ],
                references=[CRANE, RENNELS],
            ),
            MethodsSection(
                title="Branches",
                items=[
                    "Tees and wyes with lossModel 'ideal' are junctions without loss, as in "
                    "EPANET.",
                    "lossModel 'crane': the path losses follow the solved flow split with the "
                    "Crane TP-410 tee and lateral correlations (fluids.fittings."
                    "K_branch_diverging_Crane, K_run_diverging_Crane, K_branch_converging_Crane, "
                    "K_run_converging_Crane), K on the combined-flow velocity in the run "
                    "diameter; updated in the outer loop until K changes by less than "
                    f"{K_TOL:g} and the path loss by less than {OFFSET_TOL:g} m.",
                    "A tee whose combined flow passes through the branch uses the Darby 3-K tee "
                    f"'{DARBY_TEE}' per run path on its own velocity (flagged); a wye in that "
                    "pattern has no cited correlation and is reported as not converged.",
                    "Flagged outside the correlations' range: a branch larger than the run "
                    "(β > 1), unequal run pipes, a wye lateral turning against its lean, and a "
                    f"laminar combined flow (Re < {RE_LAMINAR_MAX:g} on the combined-flow "
                    "velocity in the run diameter: the Crane tee data are for turbulent flow).",
                    "Zero flow through a leg: the correlations for flow out through a leg and "
                    "flow in through it give different port heads in the limit of zero flow. A "
                    "leg whose flow reverses and reverses back between outer iterations is held "
                    "at zero flow while the head the network gives its port lies between those "
                    "two limits; its K is the one its head implies.",
                    "A flow split that keeps alternating across a step of a Crane correlation "
                    "(a split at which the fluids function switches formula, q = 0.4, 0.5 or "
                    f"0.6, and K jumps by more than {K_TOL:g}) holds K at the mean of the "
                    "fluids values at the two splits while the solved split stays between "
                    "them (flagged; the trace lists both values); a split alternating where "
                    "the correlation is continuous has its K update under-relaxed instead.",
                ],
                references=[CRANE, DARBY],
            ),
            MethodsSection(
                title="Pumps",
                items=[
                    "Head, efficiency and NPSHr curves: monotone piecewise cubic interpolation "
                    "(SciPy PchipInterpolator) through the entered points; head and NPSHr are "
                    "extrapolated along the end slope outside the points (flagged), efficiency is "
                    "held at its end values (flagged).",
                    "Speed: affinity laws, H(Q) = s² H₀(Q/s), NPSHr(Q) = s² NPSHr₀(Q/s), "
                    "η(Q) = η₀(Q/s).",
                    "No viscosity correction: the curves are used as entered for the fluid "
                    "(the Hydraulic Institute correction, ANSI/HI 9.6.7, is not in this "
                    "version).",
                    "Integral check: a pump closes when the system head exceeds its shutoff "
                    "head s² H₀(0) or the flow would reverse (EPANET 2.2 pumpstatus), and is "
                    "flagged as flow reversal.",
                    "System curve of a pump: at each flow the pump is replaced by that fixed "
                    "flow and the network solved, every other element following its own law and "
                    "status rules (other pumps keep running); the system head is EGL(discharge) "
                    "− EGL(suction). Default flows: 0 to "
                    f"{DEFAULT_RANGE_FACTOR:g} x the curve's largest flow x s. Each point "
                    "starts from the solution at the neighbouring flow (statuses, branch losses "
                    "and flows; the first from the network's own solve when the solve computes "
                    "the curves, from the initial state otherwise), so where the statuses or "
                    "branch patterns admit more than one solution the curve follows one "
                    "continuously; a point that fails from there is solved from the initial "
                    "state, and one that still has no head while the flow has a way through "
                    "(unless a control valve in series is at its switch, below) is solved again "
                    "from the initial state (if it did not start there) and from it with its "
                    "active control valves open, the first solve that gives a head, or finds a "
                    "control valve in series at its switch, being used (with none, the point "
                    "keeps its first result) and the next point starting from the result used; "
                    "a flowing point is not solved again when its flow exceeds what every way "
                    "from the pump's discharge back to its suction can pass that way (an FCV at "
                    "most its setpoint, a check valve, PRV, PSV or pump nothing in reverse: a "
                    "cut, Ford and Fulkerson), since no steady state carries it, and one whose "
                    "flow is that limit, where every steady state passes each FCV of the cut at "
                    "its setpoint, is also solved with each such FCV held open, to find whether "
                    "it sits at its switch. A point has no head where no "
                    "steady state carries its flow, where its head is undetermined (a side of "
                    "the pump with no fixed pressure, or a control valve in series at its "
                    "switch, which could also hold the flow throttled with any higher head) or "
                    "where its solve does not converge; its message says which."
                    + system_curve_control
                    + system_curve_assigned,
                    *speed_control_items,
                ],
                references=[
                    FRITSCH_CARLSON,
                    FRITSCH_BUTLAND,
                    EPANET_STATUS,
                    FORD_FULKERSON,
                    *([GALE] if assigned else []),
                    *speed_control_references,
                ],
            ),
            MethodsSection(
                title="Valves",
                items=[
                    "Open valve loss h = K v²/(2g) on the inlet pipe's inner diameter; Cv and Kv "
                    "converted with fluids.fittings.Cv_to_K / Kv_to_K (ISA-75.01.01, turbulent "
                    "flow, without the Reynolds number factor F_R); without a resistance, the "
                    "Crane TP-410 full-bore K for the valve type. A Cv, Kv or Crane K in "
                    f"laminar flow (Re < {RE_LAMINAR_MAX:g} in the inlet pipe) is flagged.",
                    "Active check valves: open loss h = Δp_crack/(ρg) + K v²/(2g); open above "
                    "their cracking head and close on reverse flow (EPANET 2.2 cvstatus with the "
                    "cracking head). A check valve locked open by the user has the open loss "
                    "K v²/(2g) only, with no cracking head and no check action; locked closed, "
                    "it passes no flow.",
                    "PRV, PSV and FCV hold the outlet static pressure, inlet static pressure or "
                    "flow when active; status rules from EPANET 2.2 (hydstatus.c) applied to the "
                    "energy grade line, with the setpoint head z + p/(ρg) + v²/(2g) at the port; "
                    "an FCV closes on reverse flow (EPANET's would pass it), and an active FCV "
                    "opens once the head across it is below its fully open loss at the setpoint "
                    "(EPANET's waits for a reverse head), as the PRV and PSV rules do. "
                    f"Control valves without a resistance: {IDEAL_CONTROL_VALVE}.",
                    f"Status tolerances: {HTOL:g} m in head, {QTOL:g} m³/s in flow.",
                    "An active state with no solution falls back to the states the valve rules "
                    "give at that solve's first iterations (EPANET 2.2 applies them at every "
                    "iteration), then to open and closed valves (EPANET's badvalve).",
                    "A section closed off by closed pumps or valves carries no flow and has no "
                    "computed pressure; the closed elements around it are re-tested against the "
                    "heads it can take at zero flow (a dead-headed pump puts its shutoff head on "
                    "it), and re-opened when no such head keeps them all closed. A PRV or PSV "
                    "inside such a section or one whose pressure level is undetermined, or closed "
                    "between two of them, keeps its state only if one set of section levels "
                    "holds it together with those closed elements and the other such valves; "
                    "otherwise the fewest of these elements change, each to the state its rule "
                    "gives at levels that hold the others (a PRV or PSV that could not be active "
                    "there, with no fixed head to draw from or deliver to, closes if open and "
                    "opens if closed).",
                ],
                references=[EPANET_STATUS, ISA_75, CRANE],
            ),
            *([reliefs] if reliefs is not None else []),
            *([equipment] if equipment is not None else []),
            *([orifices] if orifices is not None else []),
            MethodsSection(
                title="Fluid properties",
                items=[
                    f"{fluid.name}"
                    + (f" at {fluid.temperature:g} K" if fluid.temperature is not None else "")
                    + (
                        f", glycol mass fraction {fluid.concentration:g}"
                        if fluid.concentration is not None
                        else ""
                    )
                    + f": density {fluid.density:.6g} kg/m³, dynamic viscosity "
                    f"{fluid.dynamic_viscosity:.6g} Pa·s, kinematic viscosity "
                    f"{fluid.kinematic_viscosity:.6g} m²/s, vapor pressure "
                    + (
                        f"{fluid.vapor_pressure:.6g} Pa absolute."
                        if fluid.vapor_pressure is not None
                        else "not available."
                    ),
                    *(
                        f"{name}: {src.origin}, {src.citation}"
                        for name, src in fluid.sources.items()
                    ),
                    "Properties are constant throughout the network (isothermal).",
                ],
                references=[],
            ),
            MethodsSection(
                title="Atmosphere and NPSH",
                items=[
                    f"Atmospheric pressure: {p_atm_source}.",
                    "NPSH available at the pump suction port = (EGL − z) + (p_atm − p_vap)/(ρg), "
                    "the absolute static plus velocity head above the vapor pressure; margin = "
                    "NPSHa − NPSHr, flagged as cavitation when negative.",
                    "Every port's absolute static pressure is checked against the vapor "
                    "pressure (0 Pa absolute when none is known) and flagged where the liquid "
                    "would flash.",
                ],
                references=[USSA_1976],
            ),
            MethodsSection(
                title="Conventions",
                items=[
                    "SI units throughout. Pressures are gauge unless labeled absolute; "
                    "elevations and heads are measured from the single project datum.",
                    f"Gauge pressures are relative to the atmospheric pressure: {p_atm_source}.",
                    "The energy grade line EGL = z + p/(ρg) + v²/(2g) is the nodal unknown; the "
                    "hydraulic grade line HGL = EGL − v²/(2g), with v the velocity in the pipe "
                    "connected at the port. Pump head is the EGL rise.",
                    "Flow is positive from a connection's 'from' port to its 'to' port; branch "
                    "port flows are positive into the component.",
                    "Every element's trace lists its inputs (with their source: user, default, "
                    "library or computed), equations, correlations, data sources and "
                    "intermediate values.",
                ],
                references=[],
            ),
        ],
        assumptions=[
            "Steady, incompressible, isothermal, single-phase liquid flow.",
            "Reservoirs and reference nodes are quiescent bodies of liquid (velocity 0) at a "
            "constant head.",
            "No entrance or exit loss is applied where a pipe meets a reservoir or reference "
            "node unless the connection's piping has an entrance fitting ("
            + ", ".join(ENTRANCE_TYPES)
            + ") or an exit fitting ("
            + ", ".join(EXIT_TYPES)
            + "); without one, the EGL at the port equals the boundary head in either flow "
            "direction. The web app adds a sharp-edged entrance where new piping leaves a "
            "reservoir and an exit where it enters one (removable), and none at a reference "
            "node; each boundary's trace lists the entrance and exit fittings at its ports.",
            "Fluid properties are constant at the operating temperature.",
            "Pumps have an integral check: no reverse flow.",
            "Check valves: a disc that opens fully above the cracking pressure and closes on "
            "reverse flow (no partial opening).",
            "Control valves without an entered resistance are ideal: no loss when fully open.",
            "Fittings and valves without a user K use the cited correlation for the type at "
            "the connected pipe's inner diameter.",
            *([RELIEF_ASSUMPTION] if reliefs is not None else []),
            *([EQUIPMENT_ASSUMPTION] if equipment is not None else []),
            *([ORIFICE_ASSUMPTION] if orifices is not None else []),
        ],
        libraries=libraries(),
    )
