"""Friction factor and head loss calculations for pipe flow.

This module implements the Darcy-Weisbach equation for pipe friction losses
and the Colebrook equation for friction factor calculation.
"""

from __future__ import annotations

import math

from fluids.friction import friction_factor as _fluids_friction_factor

# =============================================================================
# Constants
# =============================================================================

# Gravitational acceleration
G_FT_S2 = 32.174  # ft/s²
G_M_S2 = 9.80665  # m/s²

# Flow regime boundaries (Reynolds number)
RE_LAMINAR = 2300  # Below this: laminar flow
RE_TURBULENT = 4000  # Above this: fully turbulent

# Unit conversions
GPM_TO_CFS = 1 / 448.831  # GPM to ft³/s
GPM_TO_M3S = 6.30902e-5  # GPM to m³/s
FT_TO_M = 0.3048
IN_TO_FT = 1 / 12
IN_TO_M = 0.0254


# =============================================================================
# Reynolds Number
# =============================================================================


def calculate_reynolds(
    velocity: float,
    diameter: float,
    kinematic_viscosity: float,
) -> float:
    """
    Calculate Reynolds number for pipe flow.

    Args:
        velocity: Flow velocity (same length unit as diameter / time)
        diameter: Pipe inner diameter (same length unit as velocity * time)
        kinematic_viscosity: Fluid kinematic viscosity (length²/time)

    Returns:
        Reynolds number (dimensionless)

    Note:
        Units must be consistent. If velocity is m/s and diameter is m,
        then kinematic_viscosity must be m²/s.
    """
    if kinematic_viscosity <= 0:
        raise ValueError("Kinematic viscosity must be positive")
    if diameter <= 0:
        raise ValueError("Diameter must be positive")

    return abs(velocity) * diameter / kinematic_viscosity


def calculate_velocity(
    flow_rate: float,
    diameter: float,
) -> float:
    """
    Calculate flow velocity from volumetric flow rate and pipe diameter.

    Args:
        flow_rate: Volumetric flow rate (length³/time)
        diameter: Pipe inner diameter (length)

    Returns:
        Flow velocity (length/time)

    Note:
        Units must be consistent.
    """
    if diameter <= 0:
        raise ValueError("Diameter must be positive")

    area = math.pi * (diameter / 2) ** 2
    return flow_rate / area


def calculate_velocity_fps(
    flow_gpm: float,
    diameter_in: float,
) -> float:
    """
    Calculate flow velocity in ft/s from GPM and diameter in inches.

    Args:
        flow_gpm: Volumetric flow rate in GPM
        diameter_in: Pipe inner diameter in inches

    Returns:
        Flow velocity in ft/s
    """
    # Convert GPM to ft³/s
    flow_cfs = flow_gpm * GPM_TO_CFS
    # Convert diameter to ft
    diameter_ft = diameter_in * IN_TO_FT
    return calculate_velocity(flow_cfs, diameter_ft)


# =============================================================================
# Friction Factor
# =============================================================================


def calculate_friction_factor(
    reynolds: float,
    relative_roughness: float,
) -> float:
    """
    Calculate Darcy friction factor for pipe flow.

    Uses the fluids library which implements multiple methods:
    - Laminar: f = 64/Re for Re < 2300
    - Turbulent: Colebrook-White equation for Re > 4000
    - Transition: Churchill correlation for 2300 < Re < 4000

    Args:
        reynolds: Reynolds number (dimensionless)
        relative_roughness: Pipe roughness / diameter (e/D, dimensionless)

    Returns:
        Darcy friction factor (dimensionless)

    Raises:
        ValueError: If Reynolds number is not positive
    """
    if reynolds <= 0:
        raise ValueError("Reynolds number must be positive")

    # Handle very low Reynolds (essentially zero flow)
    if reynolds < 1:
        return 64.0  # Laminar formula at Re=1

    # Use fluids library for accurate calculation
    # It handles laminar, transition, and turbulent regimes
    return _fluids_friction_factor(Re=reynolds, eD=relative_roughness)


def calculate_friction_factor_laminar(reynolds: float) -> float:
    """
    Calculate friction factor for laminar flow (Re < 2300).

    Args:
        reynolds: Reynolds number (dimensionless)

    Returns:
        Darcy friction factor = 64/Re
    """
    if reynolds <= 0:
        raise ValueError("Reynolds number must be positive")
    return 64.0 / reynolds


# =============================================================================
# Head Loss Calculations
# =============================================================================


def calculate_friction_head_loss(
    friction_factor: float,
    length: float,
    diameter: float,
    velocity: float,
    g: float = G_FT_S2,
) -> float:
    """
    Calculate friction head loss using Darcy-Weisbach equation.

    h_f = f * (L/D) * (v² / 2g)

    Args:
        friction_factor: Darcy friction factor (dimensionless)
        length: Pipe length (same unit as diameter)
        diameter: Pipe inner diameter (same unit as length)
        velocity: Flow velocity (length/time, consistent with g)
        g: Gravitational acceleration (default: 32.174 ft/s²)

    Returns:
        Head loss in same length unit as inputs
    """
    if diameter <= 0:
        raise ValueError("Diameter must be positive")
    if length < 0:
        raise ValueError("Length cannot be negative")

    return friction_factor * (length / diameter) * (velocity**2) / (2 * g)


def calculate_minor_head_loss(
    k_factor: float,
    velocity: float,
    g: float = G_FT_S2,
) -> float:
    """
    Calculate minor (fitting) head loss using K-factor method.

    h_minor = K * (v² / 2g)

    Args:
        k_factor: Sum of K-factors for all fittings (dimensionless)
        velocity: Flow velocity (length/time, consistent with g)
        g: Gravitational acceleration (default: 32.174 ft/s²)

    Returns:
        Head loss in same length unit as velocity²/g
    """
    return k_factor * (velocity**2) / (2 * g)


def calculate_total_head_loss(
    friction_factor: float,
    length: float,
    diameter: float,
    velocity: float,
    k_factor: float = 0.0,
    g: float = G_FT_S2,
) -> float:
    """
    Calculate total head loss (friction + minor losses).

    Args:
        friction_factor: Darcy friction factor (dimensionless)
        length: Pipe length (same unit as diameter)
        diameter: Pipe inner diameter (same unit as length)
        velocity: Flow velocity (length/time, consistent with g)
        k_factor: Sum of K-factors for fittings (dimensionless)
        g: Gravitational acceleration (default: 32.174 ft/s²)

    Returns:
        Total head loss in same length unit as inputs
    """
    h_friction = calculate_friction_head_loss(
        friction_factor, length, diameter, velocity, g
    )
    h_minor = calculate_minor_head_loss(k_factor, velocity, g)
    return h_friction + h_minor


# =============================================================================
# Pipe Segment Head Loss (High-Level Function)
# =============================================================================


def calculate_pipe_head_loss_fps(
    length_ft: float,
    diameter_in: float,
    roughness_in: float,
    flow_gpm: float,
    kinematic_viscosity_ft2s: float,
    k_factor: float = 0.0,
) -> tuple[float, float, float, float]:
    """
    Calculate head loss through a pipe segment using US customary units.

    This is a convenience function that handles unit conversions internally.

    Args:
        length_ft: Pipe length in feet
        diameter_in: Pipe inner diameter in inches
        roughness_in: Pipe absolute roughness in inches
        flow_gpm: Flow rate in GPM
        kinematic_viscosity_ft2s: Kinematic viscosity in ft²/s
        k_factor: Sum of K-factors for fittings (dimensionless)

    Returns:
        Tuple of (head_loss_ft, velocity_fps, reynolds, friction_factor)
    """
    if flow_gpm <= 0:
        return (0.0, 0.0, 0.0, 0.0)

    # Convert units
    diameter_ft = diameter_in * IN_TO_FT

    # Calculate velocity
    velocity_fps = calculate_velocity_fps(flow_gpm, diameter_in)

    # Calculate Reynolds number
    reynolds = calculate_reynolds(velocity_fps, diameter_ft, kinematic_viscosity_ft2s)

    # Calculate relative roughness
    relative_roughness = roughness_in / diameter_in

    # Calculate friction factor
    f = calculate_friction_factor(reynolds, relative_roughness)

    # Calculate total head loss
    h_loss = calculate_total_head_loss(
        friction_factor=f,
        length=length_ft,
        diameter=diameter_ft,
        velocity=velocity_fps,
        k_factor=k_factor,
        g=G_FT_S2,
    )

    return (h_loss, velocity_fps, reynolds, f)


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "FT_TO_M",
    "GPM_TO_CFS",
    "GPM_TO_M3S",
    # Constants
    "G_FT_S2",
    "G_M_S2",
    "IN_TO_FT",
    "IN_TO_M",
    "RE_LAMINAR",
    "RE_TURBULENT",
    # Friction factor
    "calculate_friction_factor",
    "calculate_friction_factor_laminar",
    # Head loss
    "calculate_friction_head_loss",
    "calculate_minor_head_loss",
    "calculate_pipe_head_loss_fps",
    # Reynolds number
    "calculate_reynolds",
    "calculate_total_head_loss",
    "calculate_velocity",
    "calculate_velocity_fps",
]
