"""Closed-form expected results for fluid-property and NPSH cases (design §7, §8, §12).

Fluid properties (``derivations.fluid_state``): aqueous ethylene and propylene glycol from
CoolProp ``INCOMP::MEG[x]`` / ``INCOMP::MPG[x]`` (Melinder 2010; mass fraction x; no vapor
pressure in CoolProp, so the solve carries NO_VAPOR_PRESSURE); water from CoolProp 'Water'
(IAPWS-95) with its saturation pressure as the vapor pressure; each user override replaces its
one value.

NPSH (design §8), at the suction port of elevation z_s with EGL H_s:

    NPSHa = (H_s − z_s) + (p_atm − p_vap)/(ρ g),    margin = NPSHa − NPSHr(Q)

with p_atm = settings.atmosphericPressure if given, else
``fluids.atmosphere.ATMOSPHERE_1976(siteElevation).P`` (US Standard Atmosphere 1976). CAVITATION
(invalid) when the margin is negative; BELOW_VAPOR_PRESSURE (invalid) at a node whose absolute
static pressure p + p_atm is below p_vap.

Every pipe, elevation, temperature, concentration and override is a test input. Independence:
nothing here imports ``opensolve_pipe.services``.
"""

import math
from collections.abc import Callable

from opensolve_pipe.models.fluids import BuiltinFluid, FluidOverrides
from tests.reference import derivations as dv
from tests.reference.case_format import (
    Expected,
    ReferenceCase,
    builtin_glycol,
    builtin_water,
    ideal_tee,
    make_project,
    plug,
    reservoir,
)
from tests.reference.derivations_pumps import PumpLine, curve_a, pump_line_case
from tests.reference.line import Line, require_turbulent


def _source(name: str, method: str) -> str:
    return dv.source(name, method, "derivations_fluids")


def single_line_case(
    *,
    name: str,
    title: str,
    description: str,
    method: str,
    fluid: BuiltinFluid,
    line: Line,
    h_parts: tuple[float, float, float, float],
    laminar: bool = False,
) -> ReferenceCase:
    """R1 → one line → R2 with a library fluid: H1 − H2 = h_line(Q) (brentq), or for laminar
    flow with no fittings the Hagen–Poiseuille closed form Q = ΔH g π D⁴/(128 ν L)."""
    rho, mu, p_vap = dv.fluid_state(fluid)
    nu = mu / rho
    z1, level1, z2, level2 = h_parts
    h1, h2 = z1 + level1, z2 + level2
    if laminar:
        if line.fittings:
            raise ValueError("the laminar closed form is for a plain pipe")
        q = (h1 - h2) * dv.G * math.pi * line.d**4 / (128.0 * nu * line.length)
        dv.require_regime(q, line.d, nu, "laminar")
    else:
        q = dv.solve_flow(lambda q: line.head_loss(q, nu), h1 - h2)
        require_turbulent(nu, [(q, line)])
    project = make_project(
        f"ref-{name.replace('_', '-')}",
        title,
        fluid,
        [reservoir("R1", z1, level1), reservoir("R2", z2, level2)],
        [line.connect("L1", "R1:port_1", "R2:port_1")],
    )
    flags = [] if p_vap is not None else [{"code": "NO_VAPOR_PRESSURE"}]
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": q},
        egl={"R1:port_1": h1, "R2:port_1": h2},
        vapor_pressure=p_vap,
        flags=flags,
    )
    return ReferenceCase(
        name=name,
        description=description,
        source=_source(name, method),
        project=project,
        expected=expected,
    )


def fluid_meg_solution() -> ReferenceCase:
    """30% (mass) ethylene glycol at 10 °C through a 77.9 mm line with fittings, turbulent."""
    return single_line_case(
        name="fluid_meg_solution",
        title="Ethylene glycol solution",
        description=(
            "Aqueous ethylene glycol (30% by mass, 10 C) between two reservoirs: verifies the "
            "MEG density and viscosity (CoolProp INCOMP::MEG, Melinder 2010), no vapor pressure "
            "(NO_VAPOR_PRESSURE) and the resulting flow."
        ),
        method=(
            "CoolProp PropsSI('D'/'V', T, 101325 Pa, 'INCOMP::MEG[0.3]'); Darcy-Weisbach + "
            "Colebrook; K from fluids entrance_sharp(Crane), bend_rounded_Crane, exit_normal; "
            "brentq"
        ),
        fluid=builtin_glycol("ethylene_glycol", 283.15, 0.3),
        line=Line(0.0779, 70.0, (("entrance_sharp", 1), ("elbow_90_lr", 3), ("exit", 1))),
        h_parts=(6.0, 2.0, 0.0, 1.0),
    )


def fluid_mpg_solution_laminar() -> ReferenceCase:
    """50% (mass) propylene glycol at −5 °C (above its −32 °C freezing point) in a 26.6 mm
    plain pipe: laminar, so the flow is the Hagen–Poiseuille closed form, proportional to 1/μ."""
    return single_line_case(
        name="fluid_mpg_solution_laminar",
        title="Propylene glycol solution, laminar",
        description=(
            "Cold aqueous propylene glycol (50% by mass, -5 C) in laminar flow: verifies the MPG "
            "density and viscosity (CoolProp INCOMP::MPG, Melinder 2010) through the "
            "Hagen-Poiseuille flow, which is inversely proportional to the viscosity."
        ),
        method=(
            "CoolProp PropsSI('D'/'V', T, 101325 Pa, 'INCOMP::MPG[0.5]'); Hagen-Poiseuille "
            "closed form, no iteration"
        ),
        fluid=builtin_glycol("propylene_glycol", 268.15, 0.5),
        line=Line(0.0266, 30.0),
        h_parts=(1.5, 0.5, 0.0, 1.0),
        laminar=True,
    )


def fluid_property_override() -> ReferenceCase:
    """30% propylene glycol at 5 °C with two user overrides: dynamic viscosity 4.5 mPa·s and
    vapor pressure 900 Pa. The density stays CoolProp's; each override replaces only its value
    (design §7)."""
    overrides = FluidOverrides(dynamic_viscosity=4.5e-3, vapor_pressure=900.0)
    return single_line_case(
        name="fluid_property_override",
        title="Glycol with property overrides",
        description=(
            "Propylene glycol with a user viscosity and vapor pressure: verifies that overrides "
            "replace individual properties (viscosity and vapor pressure from the user, density "
            "from CoolProp) and that the flow follows the overridden viscosity."
        ),
        method=(
            "CoolProp PropsSI('D', T, 101325 Pa, 'INCOMP::MPG[0.3]'); viscosity and vapor "
            "pressure as overridden; Darcy-Weisbach + Colebrook; brentq"
        ),
        fluid=builtin_glycol("propylene_glycol", 278.15, 0.3, overrides),
        line=Line(0.0525, 50.0, (("entrance_sharp", 1), ("exit", 1))),
        h_parts=(5.0, 2.0, 0.0, 1.0),
    )


# --- NPSH ---------------------------------------------------------------------------------------

NPSH_SUCTION = Line(0.1541, 8.0, (("entrance_sharp", 1), ("elbow_90_lr", 1)))
NPSH_DISCHARGE = Line(0.1023, 100.0, (("gate_valve", 1), ("elbow_90_lr", 2), ("exit", 1)))
NPSH_METHOD = (
    "pump curve PCHIP + affinity laws; NPSHa = (H_s - z_s) + (p_atm - p_vap)/(rho g); NPSHr "
    "PCHIP; CoolProp water (IAPWS-95) density, viscosity and saturation pressure; "
    "Darcy-Weisbach + Colebrook; brentq"
)


def npsh_margin_standard_atmosphere() -> ReferenceCase:
    """Water at 50 °C lifted 2 m from a reservoir (surface at 2 m, pump at 4 m), site at 1500 m:
    p_atm = ATMOSPHERE_1976(1500).P; positive margin."""
    line = PumpLine(0.0, 2.0, 4.0, 18.0, 2.0, NPSH_SUCTION, NPSH_DISCHARGE, curve_a())
    return pump_line_case(
        name="npsh_margin_standard_atmosphere",
        title="NPSH margin at a high site",
        description=(
            "A pump on a 2 m suction lift with 50 C water at a site 1500 m above sea level: "
            "verifies NPSH available (US Standard Atmosphere 1976 pressure, CoolProp vapor "
            "pressure, suction EGL), NPSH required from the PCHIP NPSHr curve and the margin."
        ),
        line=line,
        fluid=builtin_water(323.15),
        site_elevation=1500.0,
        npsh=True,
        method=NPSH_METHOD + "; p_atm = fluids ATMOSPHERE_1976(1500 m).P",
        module="derivations_fluids",
    )


def npsh_margin_atmospheric_override() -> ReferenceCase:
    """Water at 30 °C, pump at speed 0.9, site at 800 m but atmospheric pressure overridden to
    95 kPa (the override wins over the standard atmosphere); NPSHr = s² NPSHr₀(Q/s)."""
    line = PumpLine(0.0, 2.0, 3.5, 12.0, 2.0, NPSH_SUCTION, NPSH_DISCHARGE, curve_a(), speed=0.9)
    return pump_line_case(
        name="npsh_margin_atmospheric_override",
        title="NPSH margin with an atmospheric override",
        description=(
            "A pump at 90% speed with an atmospheric pressure override of 95 kPa: verifies that "
            "the override replaces the standard atmosphere in NPSH available and the affinity "
            "scaling of NPSH required."
        ),
        line=line,
        fluid=builtin_water(303.15),
        site_elevation=800.0,
        atmospheric_pressure_override=95000.0,
        npsh=True,
        method=NPSH_METHOD + "; p_atm = 95000 Pa override",
        module="derivations_fluids",
    )


def npsh_cavitation() -> ReferenceCase:
    """Water at 80 °C (p_vap ≈ 47 kPa) on a 2 m suction lift at 1500 m: NPSHa < NPSHr, so the
    margin is negative and CAVITATION (invalid) is expected on the pump. The suction port's
    absolute static pressure stays above p_vap (checked), so only the margin fails."""
    line = PumpLine(0.0, 1.5, 3.5, 16.0, 2.0, NPSH_SUCTION, NPSH_DISCHARGE, curve_a())
    case = pump_line_case(
        name="npsh_cavitation",
        title="Cavitating pump",
        description=(
            "Hot water (80 C) on a suction lift at a high site: verifies a negative NPSH margin "
            "and the CAVITATION flag, with the solve still returning its results."
        ),
        line=line,
        fluid=builtin_water(353.15),
        site_elevation=1500.0,
        npsh=True,
        method=NPSH_METHOD + "; p_atm = fluids ATMOSPHERE_1976(1500 m).P",
        module="derivations_fluids",
    )
    if not any(f["code"] == "CAVITATION" for f in case.expected.flags):
        raise ValueError("npsh_cavitation must cavitate")
    _, _, p_vap = dv.fluid_state(builtin_water(353.15))
    p_atm = case.expected.atmospheric_pressure
    assert p_vap is not None
    assert p_atm is not None
    if not case.expected.pressures["PU1:suction"] + p_atm > p_vap:
        raise ValueError("the suction port should stay above the vapor pressure")
    return case


def siphon_high_point_below_vapor_pressure() -> ReferenceCase:
    """A siphon: R1 (surface 5 m) → L1 up to a crest tee T1 at 14 m (ideal; branch to a plug
    0.5 m higher) → L2 down to R2 (surface −11 m). Water at 70 °C, site at sea level.

    Series flow H_R1 − H_R2 = h_L1(Q) + h_L2(Q) (brentq). At the crest p = ρg(H_T1 − z − v²/2g)
    is so far below gauge zero that p + p_atm < p_vap: the steady liquid solution is returned
    and flagged BELOW_VAPOR_PRESSURE (invalid) at the crest (design §8).
    """
    fluid = builtin_water(343.15)
    rho, mu, p_vap = dv.fluid_state(fluid)
    assert p_vap is not None
    nu = mu / rho
    l1 = Line(0.0779, 40.0, (("entrance_sharp", 1), ("elbow_90_lr", 2)))
    l2 = Line(0.0779, 60.0, (("elbow_90_lr", 2), ("exit", 1)))
    stub = Line(0.0266, 0.5)
    z1, level1, z2, level2 = 0.0, 5.0, -12.0, 1.0
    z_crest, z_plug = 14.0, 14.5
    site = 0.0
    h1, h2 = z1 + level1, z2 + level2
    q = dv.solve_flow(lambda q: l1.head_loss(q, nu) + l2.head_loss(q, nu), h1 - h2)
    require_turbulent(nu, [(q, l1), (q, l2)])
    h_crest = h1 - l1.head_loss(q, nu)
    p_atm = dv.standard_atmosphere_pressure(site)
    pressures = {
        "T1:run_inlet": dv.static_pressure(rho, h_crest, z_crest, l1.velocity(q)),
        "T1:run_outlet": dv.static_pressure(rho, h_crest, z_crest, l2.velocity(q)),
        "T1:branch": dv.static_pressure(rho, h_crest, z_crest, 0.0),
        "P1:port_1": dv.static_pressure(rho, h_crest, z_plug, 0.0),
    }
    if not all(p + p_atm < p_vap for p in pressures.values()):
        raise ValueError("every crest port must be below the vapor pressure")

    project = make_project(
        "ref-siphon-below-vapor-pressure",
        "Siphon over a high point",
        fluid,
        [
            reservoir("R1", z1, level1),
            ideal_tee("T1", z_crest),
            plug("P1", z_plug),
            reservoir("R2", z2, level2),
        ],
        [
            l1.connect("L1", "R1:port_1", "T1:run_inlet"),
            l2.connect("L2", "T1:run_outlet", "R2:port_1"),
            stub.connect("L3", "T1:branch", "P1:port_1"),
        ],
        site_elevation=site,
    )
    expected = Expected(
        density=rho,
        dynamic_viscosity=mu,
        flows={"L1": q, "L2": q, "L3": 0.0},
        egl={
            "R1:port_1": h1,
            "T1:run_inlet": h_crest,
            "T1:run_outlet": h_crest,
            "T1:branch": h_crest,
            "P1:port_1": h_crest,
            "R2:port_1": h2,
        },
        pressures=pressures,
        vapor_pressure=p_vap,
        atmospheric_pressure=p_atm,
        # One flag per port below the vapor pressure, on its component: every crest port.
        flags=[
            {"code": "BELOW_VAPOR_PRESSURE", "componentId": cid}
            for cid in sorted({key.split(":")[0] for key in pressures})
        ],
    )
    return ReferenceCase(
        name="siphon_high_point_below_vapor_pressure",
        description=(
            "A siphon whose crest, 9 m above the supply surface, runs below the vapor pressure "
            "of 70 C water: verifies sub-atmospheric static pressures at the crest, the "
            "absolute-pressure check against CoolProp's vapor pressure and the "
            "BELOW_VAPOR_PRESSURE flag."
        ),
        source=_source(
            "siphon_high_point_below_vapor_pressure",
            "CoolProp water (IAPWS-95) properties and saturation pressure; fluids "
            "ATMOSPHERE_1976(0).P; Darcy-Weisbach + Colebrook series flow; brentq",
        ),
        project=project,
        expected=expected,
    )


CASES: tuple[Callable[[], ReferenceCase], ...] = (
    fluid_meg_solution,
    fluid_mpg_solution_laminar,
    fluid_property_override,
    npsh_margin_standard_atmosphere,
    npsh_margin_atmospheric_override,
    npsh_cavitation,
    siphon_high_point_below_vapor_pressure,
)
