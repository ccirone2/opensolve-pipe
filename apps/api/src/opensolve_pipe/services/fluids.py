"""Fluid properties for the solver (SDD §3.2.2): built-in water from CoolProp, user fluids.

Water uses CoolProp's 'Water' (HEOS backend): the IAPWS-95 equation of state (Wagner & Pruß
2002) for density and saturation pressure, and the IAPWS 2008 viscosity formulation (Huber
et al. 2009). Below the normal boiling point the liquid is evaluated at standard atmospheric
pressure; at or above it, as saturated liquid (the lowest pressure at which it is liquid).
Liquid density and viscosity depend only weakly on pressure, and the solver treats the fluid
as incompressible at these properties.

Glycol solutions (CoolProp INCOMP::MEG / INCOMP::MPG) arrive in milestone M3.
"""

from functools import lru_cache

import CoolProp
from CoolProp.CoolProp import PhaseSI, PropsSI
from scipy.constants import atm

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
            state = f"liquid at {atm:g} Pa"
        else:
            rho = float(PropsSI("D", "T", temperature, "Q", 0, "Water"))
            mu = float(PropsSI("V", "T", temperature, "Q", 0, "Water"))
            state = f"saturated liquid (at or above the normal boiling point {t_boil:.4f} K)"
    except ValueError as exc:  # CoolProp reports out-of-range input as ValueError
        raise FluidError(f"water properties unavailable at {temperature:g} K: {exc}") from exc
    return rho, mu, p_vap, state


def _builtin(fluid: BuiltinFluid) -> FluidProperties:
    if fluid.fluid_id != "water":
        raise FluidError(f"built-in fluid '{fluid.fluid_id}' is not supported yet")
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
            "vaporPressure": _library(f"{_COOLPROP}, saturation pressure: {_IAPWS95}"),
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
