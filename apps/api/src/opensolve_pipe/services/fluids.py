"""Fluid properties for the solver (SDD §3.2.2): built-in water from CoolProp, user fluids.

Water uses CoolProp's 'Water' (HEOS backend): the IAPWS-95 equation of state (Wagner & Pruß
2002) for density and saturation pressure, and the IAPWS 2008 viscosity formulation (Huber
et al. 2009). Below the normal boiling point the liquid is evaluated at standard atmospheric
pressure; at or above it, as saturated liquid (the lowest pressure at which it is liquid).
Liquid density and viscosity depend only weakly on pressure, and the solver treats the fluid
as incompressible at these properties.

Aqueous ethylene and propylene glycol use CoolProp's incompressible solutions INCOMP::MEG and
INCOMP::MPG, which implement Melinder (2010): density and viscosity as functions of
temperature and glycol **mass** fraction, independent of pressure (evaluated at standard
atmospheric pressure). Only the ranges CoolProp supports are accepted, queried from CoolProp:
mass fraction in [fraction_min, fraction_max], temperature above the solution's freezing point
T_freeze(x) and within [Tmin, Tmax]. CoolProp defines no saturation pressure for these
solutions, so the vapor pressure is unknown (None) unless the user overrides it; the solve then
carries NO_VAPOR_PRESSURE and NPSH available needs that override.

Overrides (PRD §3.5.3) replace individual calculated values and are labeled 'user'.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import CoolProp
import numpy as np
from CoolProp.CoolProp import AbstractState, PhaseSI, PropsSI
from scipy.constants import atm

from ..models.api import FluidInfo, FreezingPoint, RangeInfo
from ..models.fluids import (
    BuiltinFluid,
    CustomFluid,
    FluidDefinition,
    FluidOverrides,
    FluidProperties,
    PropertySource,
)

WATER_T_MAX = 473.15
"""K. Upper end of the built-in water range (solver design §10). The lower end is CoolProp's
triple-point temperature of water, exclusive."""

_COOLPROP = f"CoolProp {CoolProp.__version__} 'Water' (HEOS)"
_IAPWS95 = (
    "IAPWS-95: W. Wagner and A. Pruß, 'The IAPWS Formulation 1995 for the Thermodynamic "
    "Properties of Ordinary Water Substance for General and Scientific Use', J. Phys. Chem. "
    "Ref. Data 31 (2002) 387-535, doi:10.1063/1.1461829"
)
_HUBER2009 = (
    "M. L. Huber et al., 'New International Formulation for the Viscosity of H2O', J. Phys. "
    "Chem. Ref. Data 38 (2009) 101-125, doi:10.1063/1.3088050"
)


_MELINDER2010 = (
    "Å. Melinder, 'Properties of Secondary Working Fluids for Indirect Systems', "
    "IIF-IIR Publishing, 2010"
)

GlycolId = Literal["ethylene_glycol", "propylene_glycol"]
GLYCOLS: dict[GlycolId, tuple[str, str]] = {
    "ethylene_glycol": ("MEG", "Ethylene glycol (aqueous)"),
    "propylene_glycol": ("MPG", "Propylene glycol (aqueous)"),
}
"""Built-in glycol id -> (CoolProp INCOMP fluid, display name)."""


class FluidError(ValueError):
    """Fluid input outside what the property source supports (HTTP 400, FLUID_ERROR)."""


def _user(citation: str) -> PropertySource:
    return PropertySource(origin="user", citation=citation)


def _library(citation: str) -> PropertySource:
    return PropertySource(origin="library", citation=citation)


@lru_cache(maxsize=512)
def _water(temperature: float) -> tuple[float, float, float, str]:
    """(density kg/m³, dynamic viscosity Pa·s, vapor pressure Pa abs, state description)."""
    t_triple = float(PropsSI("Ttriple", "Water"))
    if not t_triple < temperature <= WATER_T_MAX:
        raise FluidError(
            f"water temperature {temperature:g} K is outside the supported liquid range "
            f"({t_triple:g} K exclusive to {WATER_T_MAX:g} K)"
        )
    try:
        t_boil = float(PropsSI("T", "P", atm, "Q", 0, "Water"))
        p_vap = float(PropsSI("P", "T", temperature, "Q", 0, "Water"))
        if temperature < t_boil and PhaseSI("T", temperature, "P", atm, "Water") == "liquid":
            rho = float(PropsSI("D", "T", temperature, "P", atm, "Water"))
            mu = float(PropsSI("V", "T", temperature, "P", atm, "Water"))
            state = f"liquid at {temperature:g} K, {atm:g} Pa"
        else:
            rho = float(PropsSI("D", "T", temperature, "Q", 0, "Water"))
            mu = float(PropsSI("V", "T", temperature, "Q", 0, "Water"))
            state = (
                f"saturated liquid at {temperature:g} K (at or above the normal boiling point "
                f"{t_boil:.4f} K)"
            )
    except ValueError as exc:  # CoolProp reports out-of-range input as ValueError
        raise FluidError(f"water properties unavailable at {temperature:g} K: {exc}") from exc
    return rho, mu, p_vap, state


@dataclass(frozen=True)
class GlycolRange:
    """What CoolProp supports for one INCOMP solution (queried, not tabulated here)."""

    fraction_min: float
    fraction_max: float
    t_min: float
    t_max: float
    """K. CoolProp's bounds; the lower limit that applies is the freezing point T_freeze(x)."""


@lru_cache(maxsize=4)
def glycol_range(glycol: GlycolId) -> GlycolRange:
    """Mass-fraction and temperature limits of a glycol solution, from CoolProp: PropsSI
    'fraction_min', 'fraction_max', 'Tmin' and 'Tmax' of INCOMP::MEG / INCOMP::MPG."""
    name = f"INCOMP::{GLYCOLS[glycol][0]}"
    return GlycolRange(
        fraction_min=float(PropsSI("fraction_min", name)),
        fraction_max=float(PropsSI("fraction_max", name)),
        t_min=float(PropsSI("Tmin", name)),
        t_max=float(PropsSI("Tmax", name)),
    )


@lru_cache(maxsize=256)
def _freezing_point(fluid: str, fraction: float) -> float:
    """T_freeze [K] of an INCOMP solution at a mass fraction (CoolProp iT_freeze)."""
    state = AbstractState("INCOMP", fluid)
    state.set_mass_fractions([fraction])
    return float(state.keyed_output(CoolProp.iT_freeze))


@lru_cache(maxsize=512)
def _glycol(glycol: GlycolId, fraction: float, temperature: float) -> tuple[float, float]:
    """(density kg/m³, dynamic viscosity Pa·s) of an aqueous glycol at a mass fraction."""
    fluid = GLYCOLS[glycol][0]
    limits = glycol_range(glycol)
    if not limits.fraction_min <= fraction <= limits.fraction_max:
        raise FluidError(
            f"{GLYCOLS[glycol][1]} mass fraction {fraction:g} is outside the range CoolProp "
            f"INCOMP::{fluid} supports ({limits.fraction_min:g} to {limits.fraction_max:g})"
        )
    t_freeze = _freezing_point(fluid, fraction)
    if not (temperature > t_freeze and limits.t_min <= temperature <= limits.t_max):
        raise FluidError(
            f"{GLYCOLS[glycol][1]} at mass fraction {fraction:g}: temperature {temperature:g} K "
            f"is outside the supported liquid range (above the freezing point "
            f"{t_freeze:.6g} K, up to {limits.t_max:g} K; CoolProp INCOMP::{fluid})"
        )
    try:
        state = AbstractState("INCOMP", fluid)
        state.set_mass_fractions([fraction])
        state.update(CoolProp.PT_INPUTS, atm, temperature)
        return float(state.rhomass()), float(state.viscosity())
    except ValueError as exc:  # CoolProp reports out-of-range input as ValueError
        raise FluidError(
            f"{GLYCOLS[glycol][1]} properties unavailable at {temperature:g} K, mass fraction "
            f"{fraction:g}: {exc}"
        ) from exc


def _glycol_properties(fluid: BuiltinFluid, glycol: GlycolId) -> FluidProperties:
    if fluid.concentration is None:
        raise FluidError(
            f"{GLYCOLS[glycol][1]} needs a concentration (glycol mass fraction, 0 to 1)"
        )
    x, temperature = fluid.concentration, fluid.temperature
    rho, mu = _glycol(glycol, x, temperature)
    source = (
        f"CoolProp {CoolProp.__version__} INCOMP::{GLYCOLS[glycol][0]} at mass fraction {x:g}, "
        f"{temperature:g} K (incompressible solution fit, pressure-independent): {_MELINDER2010}"
    )
    props = FluidProperties(
        name=GLYCOLS[glycol][1],
        temperature=temperature,
        concentration=x,
        density=rho,
        dynamic_viscosity=mu,
        kinematic_viscosity=mu / rho,
        vapor_pressure=None,
        sources={
            "density": _library(source),
            "dynamicViscosity": _library(source),
            "vaporPressure": _library(
                f"not available: CoolProp INCOMP::{GLYCOLS[glycol][0]} defines no saturation "
                "pressure (give a vapor pressure override for NPSH)"
            ),
        },
    )
    return _apply_overrides(props, fluid.overrides)


def _builtin(fluid: BuiltinFluid) -> FluidProperties:
    if fluid.fluid_id != "water":
        return _glycol_properties(fluid, fluid.fluid_id)
    if fluid.concentration is not None:
        raise FluidError("concentration applies to glycol solutions only, not to water")
    rho, mu, p_vap, state = _water(fluid.temperature)
    props = FluidProperties(
        name="Water",
        temperature=fluid.temperature,
        concentration=None,
        density=rho,
        dynamic_viscosity=mu,
        kinematic_viscosity=mu / rho,
        vapor_pressure=p_vap,
        sources={
            "density": _library(f"{_COOLPROP}, {state}: {_IAPWS95}"),
            "dynamicViscosity": _library(f"{_COOLPROP}, {state}: {_HUBER2009}"),
            "vaporPressure": _library(
                f"{_COOLPROP}, saturation pressure at {fluid.temperature:g} K: {_IAPWS95}"
            ),
        },
    )
    return _apply_overrides(props, fluid.overrides)


def _apply_overrides(props: FluidProperties, overrides: FluidOverrides | None) -> FluidProperties:
    """Replace individual calculated values with the user's (PRD §3.5.3), labeled 'user'."""
    if overrides is None:
        return props
    sources = dict(props.sources)
    density, viscosity, p_vap = props.density, props.dynamic_viscosity, props.vapor_pressure
    if overrides.density is not None:
        density = overrides.density
        sources["density"] = _user("user override")
    if overrides.dynamic_viscosity is not None:
        viscosity = overrides.dynamic_viscosity
        sources["dynamicViscosity"] = _user("user override")
    if overrides.vapor_pressure is not None:
        p_vap = overrides.vapor_pressure
        sources["vaporPressure"] = _user("user override")
    return props.model_copy(
        update={
            "density": density,
            "dynamic_viscosity": viscosity,
            "kinematic_viscosity": viscosity / density,
            "vapor_pressure": p_vap,
            "sources": sources,
        }
    )


def _custom(fluid: CustomFluid) -> FluidProperties:
    return FluidProperties(
        name=fluid.name,
        temperature=fluid.temperature,
        concentration=None,
        density=fluid.density,
        dynamic_viscosity=fluid.dynamic_viscosity,
        kinematic_viscosity=fluid.dynamic_viscosity / fluid.density,
        vapor_pressure=fluid.vapor_pressure,
        sources={
            "density": _user("user-defined fluid"),
            "dynamicViscosity": _user("user-defined fluid"),
            "vaporPressure": _user(
                "user-defined fluid" if fluid.vapor_pressure is not None else "not given"
            ),
        },
    )


def fluid_properties(fluid: FluidDefinition) -> FluidProperties:
    """Resolve a project's fluid definition to the properties the solver uses.

    Raises ``FluidError`` when the input is outside the property source's range.
    """
    if isinstance(fluid, CustomFluid):
        return _custom(fluid)
    return _builtin(fluid)


FREEZING_POINT_STEP = 0.05
"""Mass-fraction spacing of the freezing points listed for each glycol (a display grid: every
value on it is CoolProp's freezing point at that fraction)."""


def _water_info() -> FluidInfo:
    t_triple = float(PropsSI("Ttriple", "Water"))
    t_boil = float(PropsSI("T", "P", atm, "Q", 0, "Water"))
    return FluidInfo(
        id="water",
        name="Water",
        temperature_range=RangeInfo(min=t_triple, max=WATER_T_MAX, unit="K"),
        concentration_range=None,
        freezing_points=None,
        vapor_pressure_available=True,
        source=f"{_COOLPROP}: density and vapor pressure {_IAPWS95}; viscosity {_HUBER2009}",
        notes=[
            f"Temperature above the triple point of water, {t_triple:g} K (CoolProp Ttriple, "
            f"exclusive), up to {WATER_T_MAX:g} K.",
            f"Below the normal boiling point ({t_boil:.6g} K at {atm:g} Pa) the properties are "
            f"those of the liquid at {atm:g} Pa; at or above it, those of the saturated liquid, "
            "so the system must be pressurized above the vapor pressure (every node is checked "
            "against it in the solve).",
            "Vapor pressure: the saturation pressure at the temperature (IAPWS-95).",
        ],
    )


def _glycol_info(glycol: GlycolId) -> FluidInfo:
    fluid, name = GLYCOLS[glycol]
    limits = glycol_range(glycol)
    count = max(round((limits.fraction_max - limits.fraction_min) / FREEZING_POINT_STEP), 1) + 1
    fractions = [
        round(x, 12) for x in np.linspace(limits.fraction_min, limits.fraction_max, count)
    ]  # round off the float noise of the grid (0.049999... -> 0.05)
    freezing = [
        FreezingPoint(concentration=x, temperature=_freezing_point(fluid, x)) for x in fractions
    ]
    lowest = min(freezing, key=lambda f: f.temperature)
    t_low = max(limits.t_min, lowest.temperature)
    return FluidInfo(
        id=glycol,
        name=name,
        temperature_range=RangeInfo(min=t_low, max=limits.t_max, unit="K"),
        concentration_range=RangeInfo(
            min=limits.fraction_min, max=limits.fraction_max, unit="mass fraction"
        ),
        freezing_points=freezing,
        vapor_pressure_available=False,
        source=(
            f"CoolProp {CoolProp.__version__} INCOMP::{fluid} (incompressible solution fit, "
            f"pressure-independent): {_MELINDER2010}"
        ),
        notes=[
            f"Glycol mass fraction {limits.fraction_min:g} to {limits.fraction_max:g} "
            f"(CoolProp fraction_min, fraction_max of INCOMP::{fluid}).",
            "The lower temperature bound depends on the concentration: it is the solution's "
            "freezing point T_freeze(x) (CoolProp iT_freeze), exclusive, and never below "
            f"CoolProp's Tmin = {limits.t_min:g} K; the upper bound is Tmax = {limits.t_max:g} K. "
            "freezingPoints lists T_freeze at fractions across the range.",
            "temperatureRange.min is the lowest of those freezing points "
            f"({lowest.temperature:.6g} K at mass fraction {lowest.concentration:g}): the lowest "
            "temperature allowed at any "
            "supported concentration, not the bound at a given one.",
            f"No vapor pressure: CoolProp INCOMP::{fluid} defines no saturation pressure, so NPSH "
            "available and flashing checks need a vapor pressure override.",
        ],
    )


@lru_cache(maxsize=1)
def fluid_list() -> tuple[FluidInfo, ...]:
    """Built-in fluids with the ranges CoolProp supports for them (GET /api/v1/fluids)."""
    return (_water_info(), _glycol_info("ethylene_glycol"), _glycol_info("propylene_glycol"))
