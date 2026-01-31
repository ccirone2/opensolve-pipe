"""K-factor resolution for pipe fittings and valves.

This module provides functions to resolve K-factors for pipe fittings
using the Crane TP-410 method (L/D or fixed K values), as well as
K-factors for valve components based on valve type and position.
"""

from __future__ import annotations

from ...models.components import ValveType
from ...models.piping import Fitting, FittingType
from ..data import get_fitting_k_factor, get_friction_factor_turbulent


def resolve_fitting_k(
    fitting: Fitting,
    nominal_diameter: float | None = None,
) -> float:
    """
    Resolve the K-factor for a single fitting.

    For L/D method fittings, requires nominal diameter to look up f_T.
    For K_fixed method fittings, returns the fixed K value directly.

    Args:
        fitting: Fitting model with type and quantity
        nominal_diameter: Pipe nominal diameter in inches (for L/D method)

    Returns:
        Total K-factor for the fitting (K * quantity)
    """
    k_single = get_fitting_k_factor(
        fitting_type=fitting.type,
        nominal_diameter=nominal_diameter,
    )
    return k_single * fitting.quantity


def resolve_fittings_total_k(
    fittings: list[Fitting],
    nominal_diameter: float,
) -> float:
    """
    Calculate total K-factor for a list of fittings.

    Args:
        fittings: List of Fitting models
        nominal_diameter: Pipe nominal diameter in inches

    Returns:
        Sum of K-factors for all fittings
    """
    return sum(resolve_fitting_k(fitting, nominal_diameter) for fitting in fittings)


def get_fitting_k_by_type(
    fitting_type: FittingType | str,
    nominal_diameter: float | None = None,
    quantity: int = 1,
) -> float:
    """
    Get K-factor for a fitting type.

    Convenience function that doesn't require creating a Fitting model.

    Args:
        fitting_type: Type of fitting (enum or string)
        nominal_diameter: Pipe nominal diameter in inches (for L/D method)
        quantity: Number of fittings

    Returns:
        Total K-factor (K * quantity)
    """
    k_single = get_fitting_k_factor(
        fitting_type=fitting_type,
        nominal_diameter=nominal_diameter,
    )
    return k_single * quantity


def get_f_t(nominal_diameter: float) -> float:
    """
    Get friction factor at complete turbulence (f_T) for a pipe size.

    This is used for L/D method K-factor calculations.

    Args:
        nominal_diameter: Pipe nominal diameter in inches

    Returns:
        f_T value (dimensionless)
    """
    return get_friction_factor_turbulent(nominal_diameter)


# =============================================================================
# Common Fitting K-Factor Lookups
# =============================================================================


def k_elbow_90_lr(nominal_diameter: float, quantity: int = 1) -> float:
    """K-factor for 90° long radius elbow."""
    return get_fitting_k_by_type(FittingType.ELBOW_90_LR, nominal_diameter, quantity)


def k_elbow_90_sr(nominal_diameter: float, quantity: int = 1) -> float:
    """K-factor for 90° short radius elbow."""
    return get_fitting_k_by_type(FittingType.ELBOW_90_SR, nominal_diameter, quantity)


def k_elbow_45(nominal_diameter: float, quantity: int = 1) -> float:
    """K-factor for 45° elbow."""
    return get_fitting_k_by_type(FittingType.ELBOW_45, nominal_diameter, quantity)


def k_gate_valve(nominal_diameter: float, quantity: int = 1) -> float:
    """K-factor for gate valve (fully open)."""
    return get_fitting_k_by_type(FittingType.GATE_VALVE, nominal_diameter, quantity)


def k_ball_valve(nominal_diameter: float, quantity: int = 1) -> float:
    """K-factor for ball valve (fully open)."""
    return get_fitting_k_by_type(FittingType.BALL_VALVE, nominal_diameter, quantity)


def k_check_valve_swing(nominal_diameter: float, quantity: int = 1) -> float:
    """K-factor for swing check valve."""
    return get_fitting_k_by_type(
        FittingType.CHECK_VALVE_SWING, nominal_diameter, quantity
    )


def k_entrance_sharp(quantity: int = 1) -> float:
    """K-factor for sharp-edged pipe entrance."""
    # K_fixed method - doesn't need diameter
    return get_fitting_k_by_type(FittingType.ENTRANCE_SHARP, None, quantity)


def k_entrance_rounded(quantity: int = 1) -> float:
    """K-factor for rounded pipe entrance."""
    return get_fitting_k_by_type(FittingType.ENTRANCE_ROUNDED, None, quantity)


def k_exit(quantity: int = 1) -> float:
    """K-factor for pipe exit."""
    return get_fitting_k_by_type(FittingType.EXIT, None, quantity)


# =============================================================================
# Valve K-Factor Lookups
# =============================================================================


def get_valve_k_factor(
    valve_type: ValveType,
    position: float | None = None,
) -> float:
    """Get K-factor for valve based on type and position.

    Uses base K-factors from Crane TP-410 for fully open valves,
    then adjusts for valve position using a simplified model.

    Args:
        valve_type: Type of valve
        position: Valve position (0=closed, 1=open), None for full open

    Returns:
        K-factor for head loss calculation
    """
    # Base K-factors for fully open valves (from Crane TP-410)
    base_k: dict[ValveType, float] = {
        ValveType.GATE: 0.2,
        ValveType.BALL: 0.05,
        ValveType.BUTTERFLY: 0.3,
        ValveType.GLOBE: 10.0,
        ValveType.CHECK: 2.5,
        ValveType.STOP_CHECK: 13.0,
        ValveType.PRV: 5.0,
        ValveType.PSV: 5.0,
        ValveType.FCV: 3.0,
        ValveType.TCV: 3.0,
        ValveType.RELIEF: 2.0,
    }

    k = base_k.get(valve_type, 1.0)

    # Adjust for position (simplified model)
    if position is not None and position < 1.0:
        # K increases as valve closes (simplified exponential model)
        # At 50% open, K is roughly 4x the full-open value
        if position <= 0:
            return float("inf")  # Closed valve
        k = k / (position**2)

    return k


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "get_f_t",
    "get_fitting_k_by_type",
    "get_valve_k_factor",
    "k_ball_valve",
    "k_check_valve_swing",
    "k_elbow_45",
    # Common fitting lookups
    "k_elbow_90_lr",
    "k_elbow_90_sr",
    "k_entrance_rounded",
    "k_entrance_sharp",
    "k_exit",
    "k_gate_valve",
    "resolve_fitting_k",
    "resolve_fittings_total_k",
]
