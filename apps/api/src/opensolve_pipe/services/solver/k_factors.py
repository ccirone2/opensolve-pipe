"""K-factor resolution for pipe fittings.

This module provides functions to resolve K-factors for pipe fittings
using the Crane TP-410 method (L/D or fixed K values).
"""

from __future__ import annotations

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
# Exports
# =============================================================================

__all__ = [
    "get_f_t",
    "get_fitting_k_by_type",
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
