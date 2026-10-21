"""Fluid properties: CoolProp water, custom fluids, overrides, out-of-range input."""

import pytest
from CoolProp.CoolProp import PropsSI
from scipy.constants import atm

from opensolve_pipe.models.fluids import BuiltinFluid, CustomFluid
from opensolve_pipe.services.fluids import WATER_T_MAX, FluidError, fluid_properties, glycol_range


def water(temperature: float, **kwargs: object) -> BuiltinFluid:
    return BuiltinFluid.model_validate(
        {"kind": "builtin", "fluidId": "water", "temperature": temperature, **kwargs}
    )


@pytest.mark.parametrize("temperature", [273.2, 293.15, 313.15, 353.15, 373.0])
def test_water_below_boiling_is_coolprop_liquid_at_one_atmosphere(temperature: float) -> None:
    props = fluid_properties(water(temperature))
    assert props.density == PropsSI("D", "T", temperature, "P", atm, "Water")
    assert props.dynamic_viscosity == PropsSI("V", "T", temperature, "P", atm, "Water")
    assert props.kinematic_viscosity == props.dynamic_viscosity / props.density
    assert props.vapor_pressure == PropsSI("P", "T", temperature, "Q", 0, "Water")
    assert props.temperature == temperature
    assert props.name == "Water"
    for key in ("density", "dynamicViscosity", "vaporPressure"):
        assert props.sources[key].origin == "library"
        assert "IAPWS" in props.sources[key].citation or "Huber" in props.sources[key].citation
    assert "Huber" in props.sources["dynamicViscosity"].citation
    assert "Wagner" in props.sources["density"].citation


@pytest.mark.parametrize("temperature", [380.0, 450.0, WATER_T_MAX])
def test_water_above_boiling_is_saturated_liquid(temperature: float) -> None:
    props = fluid_properties(water(temperature))
    assert props.density == PropsSI("D", "T", temperature, "Q", 0, "Water")
    assert props.dynamic_viscosity == PropsSI("V", "T", temperature, "Q", 0, "Water")
    assert props.vapor_pressure == PropsSI("P", "T", temperature, "Q", 0, "Water")
    assert "saturated liquid" in props.sources["density"].citation


@pytest.mark.parametrize(
    "temperature", [PropsSI("Ttriple", "Water"), 273.15, 200.0, WATER_T_MAX + 1e-6, 600.0]
)
def test_water_outside_its_range_is_a_fluid_error(temperature: float) -> None:
    with pytest.raises(FluidError, match="outside the supported liquid range"):
        fluid_properties(water(temperature))


def test_fluid_error_is_a_value_error() -> None:
    assert issubclass(FluidError, ValueError)


def glycol(
    fluid_id: str, temperature: float, concentration: float | None, **kw: object
) -> BuiltinFluid:
    return BuiltinFluid.model_validate(
        {
            "kind": "builtin",
            "fluidId": fluid_id,
            "temperature": temperature,
            "concentration": concentration,
            **kw,
        }
    )


GLYCOL_IDS = {"ethylene_glycol": "MEG", "propylene_glycol": "MPG"}


@pytest.mark.parametrize("fluid_id", sorted(GLYCOL_IDS))
@pytest.mark.parametrize(("x", "temperature"), [(0.0, 293.15), (0.3, 263.15), (0.5, 353.15)])
def test_glycol_properties_are_coolprop_incomp(fluid_id: str, x: float, temperature: float) -> None:
    """Density and viscosity equal direct PropsSI calls on INCOMP::MEG[x] / MPG[x] (the
    string form, another CoolProp path than the service's AbstractState)."""
    name = f"INCOMP::{GLYCOL_IDS[fluid_id]}[{x}]"
    props = fluid_properties(glycol(fluid_id, temperature, x))
    assert props.density == pytest.approx(PropsSI("D", "T", temperature, "P", atm, name), rel=1e-14)
    assert props.dynamic_viscosity == pytest.approx(
        PropsSI("V", "T", temperature, "P", atm, name), rel=1e-14
    )
    assert props.kinematic_viscosity == props.dynamic_viscosity / props.density
    assert props.concentration == x
    assert props.vapor_pressure is None
    assert "Melinder" in props.sources["density"].citation
    assert f"INCOMP::{GLYCOL_IDS[fluid_id]}" in props.sources["dynamicViscosity"].citation
    assert "not available" in props.sources["vaporPressure"].citation


@pytest.mark.parametrize("fluid_id", sorted(GLYCOL_IDS))
def test_glycol_ranges_are_queried_from_coolprop(fluid_id: str) -> None:
    name = f"INCOMP::{GLYCOL_IDS[fluid_id]}"
    limits = glycol_range(fluid_id)  # type: ignore[arg-type]
    assert limits.fraction_min == PropsSI("fraction_min", name)
    assert limits.fraction_max == PropsSI("fraction_max", name)
    assert limits.t_min == PropsSI("Tmin", name)
    assert limits.t_max == PropsSI("Tmax", name)


@pytest.mark.parametrize("fluid_id", sorted(GLYCOL_IDS))
def test_glycol_outside_coolprops_range_is_a_fluid_error(fluid_id: str) -> None:
    name = f"INCOMP::{GLYCOL_IDS[fluid_id]}"
    x_max = PropsSI("fraction_max", name)
    t_max = PropsSI("Tmax", name)
    t_freeze = PropsSI("T_freeze", f"{name}[0.3]")
    with pytest.raises(FluidError, match="mass fraction"):
        fluid_properties(glycol(fluid_id, 293.15, x_max + 0.01))
    with pytest.raises(FluidError, match="freezing point"):
        fluid_properties(glycol(fluid_id, t_freeze - 0.01, 0.3))
    with pytest.raises(FluidError, match="freezing point"):
        fluid_properties(glycol(fluid_id, t_freeze, 0.3))  # at T_freeze: not above it
    with pytest.raises(FluidError, match="outside the supported liquid range"):
        fluid_properties(glycol(fluid_id, t_max + 0.01, 0.3))
    with pytest.raises(FluidError, match="needs a concentration"):
        fluid_properties(glycol(fluid_id, 293.15, None))
    # Just inside the limits is accepted.
    fluid_properties(glycol(fluid_id, t_freeze + 0.01, 0.3))
    fluid_properties(glycol(fluid_id, t_max, x_max))


def test_glycol_overrides_supply_the_missing_vapor_pressure() -> None:
    base = fluid_properties(glycol("ethylene_glycol", 293.15, 0.3))
    props = fluid_properties(
        glycol("ethylene_glycol", 293.15, 0.3, overrides={"vaporPressure": 1800.0})
    )
    assert props.vapor_pressure == 1800.0
    assert props.sources["vaporPressure"].origin == "user"
    assert props.density == base.density
    assert props.sources["density"].origin == "library"


def test_water_rejects_a_concentration() -> None:
    with pytest.raises(FluidError, match="glycol solutions only"):
        fluid_properties(water(293.15, concentration=0.2))


def test_overrides_replace_individual_values() -> None:
    base = fluid_properties(water(293.15))
    props = fluid_properties(water(293.15, overrides={"density": 1000.0}))
    assert props.density == 1000.0
    assert props.sources["density"].origin == "user"
    assert props.dynamic_viscosity == base.dynamic_viscosity
    assert props.sources["dynamicViscosity"].origin == "library"
    assert props.kinematic_viscosity == base.dynamic_viscosity / 1000.0
    props = fluid_properties(
        water(293.15, overrides={"dynamicViscosity": 2e-3, "vaporPressure": 5000.0})
    )
    assert (props.dynamic_viscosity, props.vapor_pressure) == (2e-3, 5000.0)
    assert props.sources["vaporPressure"].origin == "user"


def test_custom_fluid_uses_the_user_values() -> None:
    fluid = CustomFluid(
        kind="custom", name="oil", density=850.0, dynamic_viscosity=0.02, vapor_pressure=100.0
    )
    props = fluid_properties(fluid)
    assert (props.density, props.dynamic_viscosity, props.vapor_pressure) == (850.0, 0.02, 100.0)
    assert props.kinematic_viscosity == 0.02 / 850.0
    assert all(s.origin == "user" for s in props.sources.values())
    no_pvap = fluid_properties(CustomFluid(kind="custom", name="x", density=1, dynamic_viscosity=1))
    assert no_pvap.vapor_pressure is None
    assert no_pvap.sources["vaporPressure"].citation == "not given"
