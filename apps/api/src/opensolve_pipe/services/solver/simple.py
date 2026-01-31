"""Simple solver for single-path hydraulic networks.

This module implements the core hydraulic calculation engine for networks
without branches (single flow path from source to sink).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.optimize import brentq

from ..fluids import get_water_properties
from .friction import (
    calculate_pipe_head_loss_fps,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from ...models.fluids import FluidProperties
    from ...models.pump import FlowHeadPoint


# =============================================================================
# Solver Options
# =============================================================================


@dataclass
class SimpleSolverOptions:
    """Configuration options for the simple solver."""

    max_iterations: int = 100
    tolerance: float = 0.001
    flow_min_gpm: float = 0.1
    flow_max_gpm: float = 1000.0
    num_curve_points: int = 51
    atmospheric_pressure_psi: float = 14.696


@dataclass
class SolverResult:
    """Result from the simple solver."""

    converged: bool
    iterations: int = 0
    error_message: str | None = None

    # Operating point
    operating_flow_gpm: float | None = None
    operating_head_ft: float | None = None

    # System curve data (for visualization)
    system_curve: list[tuple[float, float]] = field(default_factory=list)
    pump_curve: list[tuple[float, float]] = field(default_factory=list)

    # Detailed results
    velocity_fps: float | None = None
    reynolds_number: float | None = None
    friction_factor: float | None = None
    total_head_loss_ft: float | None = None
    static_head_ft: float | None = None

    # NPSH
    npsh_available_ft: float | None = None


# =============================================================================
# Pump Curve Interpolation
# =============================================================================


def build_pump_curve_interpolator(
    curve_points: list[FlowHeadPoint],
) -> Callable[[float], float]:
    """
    Build an interpolator function for a pump curve.

    Uses cubic spline interpolation for smooth curve.

    Args:
        curve_points: List of pump curve points (flow, head pairs)

    Returns:
        Function that takes flow (GPM) and returns head (ft)

    Raises:
        ValueError: If curve has fewer than 2 points
    """
    if len(curve_points) < 2:
        raise ValueError("Pump curve must have at least 2 points")

    # Sort by flow rate
    sorted_points = sorted(curve_points, key=lambda p: p.flow)

    flows = np.array([p.flow for p in sorted_points])
    heads = np.array([p.head for p in sorted_points])

    # Create cubic spline interpolator
    # Use natural boundary conditions (second derivative = 0 at ends)
    spline = CubicSpline(flows, heads, bc_type="natural")

    def interpolator(flow: float) -> float:
        # Extrapolate linearly beyond curve bounds
        if flow < flows[0]:
            # Extrapolate from shutoff (assume flat or slightly rising)
            return float(heads[0])
        if flow > flows[-1]:
            # Extrapolate beyond max flow (curve drops off)
            slope = (heads[-1] - heads[-2]) / (flows[-1] - flows[-2])
            return float(heads[-1] + slope * (flow - flows[-1]))
        return float(spline(flow))

    return interpolator


# =============================================================================
# System Curve Generation
# =============================================================================


def generate_system_curve(
    static_head_ft: float,
    pipe_length_ft: float,
    pipe_diameter_in: float,
    pipe_roughness_in: float,
    kinematic_viscosity_ft2s: float,
    total_k_factor: float = 0.0,
    flow_min_gpm: float = 0.1,
    flow_max_gpm: float = 500.0,
    num_points: int = 51,
) -> list[tuple[float, float]]:
    """
    Generate system curve as list of (flow, head) pairs.

    System head = static head + friction losses + minor losses

    Args:
        static_head_ft: Static head (elevation difference) in feet
        pipe_length_ft: Total equivalent pipe length in feet
        pipe_diameter_in: Pipe inner diameter in inches
        pipe_roughness_in: Pipe absolute roughness in inches
        kinematic_viscosity_ft2s: Fluid kinematic viscosity in ft²/s
        total_k_factor: Sum of K-factors for all fittings
        flow_min_gpm: Minimum flow rate for curve
        flow_max_gpm: Maximum flow rate for curve
        num_points: Number of points on curve

    Returns:
        List of (flow_gpm, head_ft) tuples
    """
    flows = np.linspace(flow_min_gpm, flow_max_gpm, num_points)
    curve = []

    for flow_gpm in flows:
        h_loss, _, _, _ = calculate_pipe_head_loss_fps(
            length_ft=pipe_length_ft,
            diameter_in=pipe_diameter_in,
            roughness_in=pipe_roughness_in,
            flow_gpm=flow_gpm,
            kinematic_viscosity_ft2s=kinematic_viscosity_ft2s,
            k_factor=total_k_factor,
        )
        total_head = static_head_ft + h_loss
        curve.append((float(flow_gpm), total_head))

    return curve


def build_system_curve_function(
    static_head_ft: float,
    pipe_length_ft: float,
    pipe_diameter_in: float,
    pipe_roughness_in: float,
    kinematic_viscosity_ft2s: float,
    total_k_factor: float = 0.0,
) -> Callable[[float], float]:
    """
    Build a function that calculates system head at any flow rate.

    Args:
        static_head_ft: Static head (elevation difference) in feet
        pipe_length_ft: Total equivalent pipe length in feet
        pipe_diameter_in: Pipe inner diameter in inches
        pipe_roughness_in: Pipe absolute roughness in inches
        kinematic_viscosity_ft2s: Fluid kinematic viscosity in ft²/s
        total_k_factor: Sum of K-factors for all fittings

    Returns:
        Function that takes flow (GPM) and returns system head (ft)
    """

    def system_head(flow_gpm: float) -> float:
        if flow_gpm <= 0:
            return static_head_ft

        h_loss, _, _, _ = calculate_pipe_head_loss_fps(
            length_ft=pipe_length_ft,
            diameter_in=pipe_diameter_in,
            roughness_in=pipe_roughness_in,
            flow_gpm=flow_gpm,
            kinematic_viscosity_ft2s=kinematic_viscosity_ft2s,
            k_factor=total_k_factor,
        )
        return static_head_ft + h_loss

    return system_head


# =============================================================================
# Operating Point
# =============================================================================


def find_operating_point(
    pump_curve: Callable[[float], float],
    system_curve: Callable[[float], float],
    flow_min: float = 0.1,
    flow_max: float = 1000.0,
    tolerance: float = 0.001,
) -> tuple[float, float] | None:
    """
    Find the operating point where pump and system curves intersect.

    Uses Brent's method for root finding.

    Args:
        pump_curve: Function returning pump head at given flow
        system_curve: Function returning system head at given flow
        flow_min: Minimum flow to search
        flow_max: Maximum flow to search
        tolerance: Convergence tolerance

    Returns:
        Tuple of (flow_gpm, head_ft) at operating point, or None if no solution
    """

    def difference(flow: float) -> float:
        return pump_curve(flow) - system_curve(flow)

    # Check if there's a sign change (solution exists)
    diff_min = difference(flow_min)
    diff_max = difference(flow_max)

    # If pump head at min flow is below system head, pump can't overcome static
    if diff_min < 0:
        return None

    # If pump head at max flow is still above system head, operating beyond curve
    if diff_max > 0:
        # Try to find where they cross, may be beyond max flow
        # For safety, return the max flow point
        return (flow_max, pump_curve(flow_max))

    # Use Brent's method to find the intersection
    try:
        operating_flow = brentq(difference, flow_min, flow_max, xtol=tolerance)
        operating_head = pump_curve(operating_flow)
        return (operating_flow, operating_head)
    except ValueError:
        # No sign change found - curves don't intersect in range
        return None


# =============================================================================
# NPSH Calculation
# =============================================================================


def calculate_npsh_available(
    atmospheric_pressure_psi: float,
    suction_head_ft: float,
    suction_losses_ft: float,
    vapor_pressure_psi: float,
    fluid_specific_gravity: float = 1.0,
) -> float:
    """
    Calculate Net Positive Suction Head Available (NPSHa).

    NPSHa = P_atm/gamma + H_s - h_f - P_v/gamma

    Where:
        P_atm = atmospheric pressure
        H_s = static suction head (positive if liquid above pump)
        h_f = friction losses in suction piping
        P_v = vapor pressure of liquid
        gamma = specific weight of liquid

    Args:
        atmospheric_pressure_psi: Atmospheric pressure in psi
        suction_head_ft: Static suction head in ft (positive = flooded suction)
        suction_losses_ft: Friction losses in suction piping in ft
        vapor_pressure_psi: Fluid vapor pressure in psi
        fluid_specific_gravity: Fluid specific gravity (1.0 for water)

    Returns:
        NPSH available in feet
    """
    # Convert pressure to head (ft of fluid)
    # h = P / (gamma * SG) where gamma = 0.433 psi/ft for water
    gamma = 0.433 * fluid_specific_gravity  # psi per ft of fluid

    p_atm_head = atmospheric_pressure_psi / gamma
    p_vapor_head = vapor_pressure_psi / gamma

    npsh_a = p_atm_head + suction_head_ft - suction_losses_ft - p_vapor_head
    return npsh_a


# =============================================================================
# VFD Pump Control (Affinity Laws)
# =============================================================================


@dataclass
class VFDControlResult:
    """Result from VFD speed control calculation."""

    converged: bool
    actual_speed: float
    operating_flow_gpm: float | None = None
    operating_head_ft: float | None = None
    setpoint_achieved: bool = False
    actual_value: float | None = None  # Actual pressure or flow achieved
    error_message: str | None = None


def apply_affinity_laws(
    curve_points: list[FlowHeadPoint],
    speed_ratio: float,
) -> list[FlowHeadPoint]:
    """
    Apply affinity laws to shift pump curve for different speed.

    Affinity laws:
        Q₂/Q₁ = N₂/N₁
        H₂/H₁ = (N₂/N₁)²
        P₂/P₁ = (N₂/N₁)³

    Args:
        curve_points: Original pump curve points at rated speed
        speed_ratio: Speed ratio (0.3 to 1.2 typical), 1.0 = rated speed

    Returns:
        New pump curve points at the adjusted speed
    """
    from ...models.pump import FlowHeadPoint as FHP

    adjusted_points = []
    for point in curve_points:
        new_flow = point.flow * speed_ratio
        new_head = point.head * (speed_ratio**2)
        adjusted_points.append(FHP(flow=new_flow, head=new_head))
    return adjusted_points


def build_speed_adjusted_pump_curve(
    curve_points: list[FlowHeadPoint],
    speed_ratio: float,
) -> Callable[[float], float]:
    """
    Build pump curve interpolator at a specific speed ratio.

    Args:
        curve_points: Original pump curve points at rated speed
        speed_ratio: Speed ratio (1.0 = rated speed)

    Returns:
        Function that takes flow (GPM) and returns head (ft)
    """
    adjusted_points = apply_affinity_laws(curve_points, speed_ratio)
    return build_pump_curve_interpolator(adjusted_points)


def find_vfd_speed_for_flow(
    curve_points: list[FlowHeadPoint],
    system_curve_func: Callable[[float], float],
    target_flow_gpm: float,
    speed_min: float = 0.3,
    speed_max: float = 1.2,
    tolerance: float = 0.01,
    max_iterations: int = 50,
) -> VFDControlResult:
    """
    Find VFD speed to achieve target flow rate.

    Iteratively adjusts speed until pump delivers target flow at the
    intersection of adjusted pump curve and system curve.

    Args:
        curve_points: Original pump curve points at rated speed
        system_curve_func: System curve function (flow -> head)
        target_flow_gpm: Target flow rate in GPM
        speed_min: Minimum allowed speed ratio
        speed_max: Maximum allowed speed ratio
        tolerance: Flow tolerance as fraction of target
        max_iterations: Maximum iterations

    Returns:
        VFDControlResult with actual speed and operating point
    """
    # Binary search for speed that achieves target flow
    low_speed = speed_min
    high_speed = speed_max

    # Check if target is achievable at max speed
    max_speed_curve = build_speed_adjusted_pump_curve(curve_points, high_speed)
    max_speed_point = find_operating_point(
        max_speed_curve, system_curve_func, flow_max=target_flow_gpm * 2
    )
    if max_speed_point is None or max_speed_point[0] < target_flow_gpm:
        return VFDControlResult(
            converged=False,
            actual_speed=high_speed,
            operating_flow_gpm=max_speed_point[0] if max_speed_point else None,
            operating_head_ft=max_speed_point[1] if max_speed_point else None,
            setpoint_achieved=False,
            error_message=f"Target flow {target_flow_gpm} GPM not achievable at max speed",
        )

    # Check if target is too low even at min speed
    min_speed_curve = build_speed_adjusted_pump_curve(curve_points, low_speed)
    min_speed_point = find_operating_point(
        min_speed_curve, system_curve_func, flow_max=target_flow_gpm * 2
    )
    if min_speed_point and min_speed_point[0] > target_flow_gpm:
        return VFDControlResult(
            converged=True,
            actual_speed=low_speed,
            operating_flow_gpm=min_speed_point[0],
            operating_head_ft=min_speed_point[1],
            setpoint_achieved=False,
            actual_value=min_speed_point[0],
            error_message=f"Target flow {target_flow_gpm} GPM requires speed below minimum",
        )

    # Binary search
    for _ in range(max_iterations):
        mid_speed = (low_speed + high_speed) / 2
        pump_curve = build_speed_adjusted_pump_curve(curve_points, mid_speed)
        op_point = find_operating_point(
            pump_curve, system_curve_func, flow_max=target_flow_gpm * 3
        )

        if op_point is None:
            low_speed = mid_speed
            continue

        actual_flow = op_point[0]
        error = abs(actual_flow - target_flow_gpm) / target_flow_gpm

        if error < tolerance:
            return VFDControlResult(
                converged=True,
                actual_speed=mid_speed,
                operating_flow_gpm=actual_flow,
                operating_head_ft=op_point[1],
                setpoint_achieved=True,
                actual_value=actual_flow,
            )

        if actual_flow > target_flow_gpm:
            high_speed = mid_speed
        else:
            low_speed = mid_speed

    # Return best result after max iterations
    final_speed = (low_speed + high_speed) / 2
    pump_curve = build_speed_adjusted_pump_curve(curve_points, final_speed)
    final_point = find_operating_point(pump_curve, system_curve_func)
    return VFDControlResult(
        converged=True,
        actual_speed=final_speed,
        operating_flow_gpm=final_point[0] if final_point else None,
        operating_head_ft=final_point[1] if final_point else None,
        setpoint_achieved=False,
        actual_value=final_point[0] if final_point else None,
        error_message="Max iterations reached",
    )


def find_vfd_speed_for_pressure(
    curve_points: list[FlowHeadPoint],
    system_curve_func: Callable[[float], float],
    target_discharge_pressure_ft: float,
    suction_head_ft: float,
    speed_min: float = 0.3,
    speed_max: float = 1.2,
    tolerance: float = 0.01,
    max_iterations: int = 50,
) -> VFDControlResult:
    """
    Find VFD speed to achieve target discharge pressure.

    Discharge pressure = suction head + pump head

    Args:
        curve_points: Original pump curve points at rated speed
        system_curve_func: System curve function (flow -> head)
        target_discharge_pressure_ft: Target discharge pressure in ft of head
        suction_head_ft: Suction head (pressure at pump inlet) in ft
        speed_min: Minimum allowed speed ratio
        speed_max: Maximum allowed speed ratio
        tolerance: Pressure tolerance as fraction of target
        max_iterations: Maximum iterations

    Returns:
        VFDControlResult with actual speed and operating point
    """
    # Target pump head = target discharge - suction
    target_pump_head = target_discharge_pressure_ft - suction_head_ft

    # Binary search for speed
    low_speed = speed_min
    high_speed = speed_max

    for _ in range(max_iterations):
        mid_speed = (low_speed + high_speed) / 2
        pump_curve = build_speed_adjusted_pump_curve(curve_points, mid_speed)
        op_point = find_operating_point(pump_curve, system_curve_func)

        if op_point is None:
            low_speed = mid_speed
            continue

        actual_head = op_point[1]
        actual_discharge = suction_head_ft + actual_head
        error = abs(actual_head - target_pump_head) / max(target_pump_head, 1.0)

        if error < tolerance:
            return VFDControlResult(
                converged=True,
                actual_speed=mid_speed,
                operating_flow_gpm=op_point[0],
                operating_head_ft=actual_head,
                setpoint_achieved=True,
                actual_value=actual_discharge,
            )

        if actual_head > target_pump_head:
            high_speed = mid_speed
        else:
            low_speed = mid_speed

    # Return best result after max iterations
    final_speed = (low_speed + high_speed) / 2
    pump_curve = build_speed_adjusted_pump_curve(curve_points, final_speed)
    final_point = find_operating_point(pump_curve, system_curve_func)
    actual_discharge = (
        suction_head_ft + final_point[1] if final_point else suction_head_ft
    )
    return VFDControlResult(
        converged=True,
        actual_speed=final_speed,
        operating_flow_gpm=final_point[0] if final_point else None,
        operating_head_ft=final_point[1] if final_point else None,
        setpoint_achieved=False,
        actual_value=actual_discharge,
        error_message="Max iterations reached",
    )


# =============================================================================
# Simple Solver (Main Entry Point)
# =============================================================================


def solve_pump_pipe_system(
    pump_curve_points: list[FlowHeadPoint],
    static_head_ft: float,
    pipe_length_ft: float,
    pipe_diameter_in: float,
    pipe_roughness_in: float,
    fluid_properties: FluidProperties,
    total_k_factor: float = 0.0,
    suction_head_ft: float = 0.0,
    suction_losses_ft: float = 0.0,
    options: SimpleSolverOptions | None = None,
) -> SolverResult:
    """
    Solve a simple pump-pipe system to find operating point.

    This is the main entry point for solving single-path networks.

    Args:
        pump_curve_points: Pump performance curve points
        static_head_ft: Total static head (discharge elev - suction elev)
        pipe_length_ft: Total pipe length in feet
        pipe_diameter_in: Pipe inner diameter in inches
        pipe_roughness_in: Pipe absolute roughness in inches
        fluid_properties: Fluid properties (density, viscosity, etc.)
        total_k_factor: Sum of K-factors for all fittings
        suction_head_ft: Static suction head (positive = flooded)
        suction_losses_ft: Friction losses in suction piping
        options: Solver configuration options

    Returns:
        SolverResult with operating point and detailed results
    """
    if options is None:
        options = SimpleSolverOptions()

    # Convert kinematic viscosity to ft²/s
    # FluidProperties has m²/s, need to convert
    nu_ft2s = fluid_properties.kinematic_viscosity * 10.7639  # m²/s to ft²/s

    # Convert vapor pressure to psi
    vapor_pressure_psi = fluid_properties.vapor_pressure * 0.000145038  # Pa to psi

    try:
        # Build pump curve interpolator
        pump_interp = build_pump_curve_interpolator(pump_curve_points)

        # Build system curve function
        system_func = build_system_curve_function(
            static_head_ft=static_head_ft,
            pipe_length_ft=pipe_length_ft,
            pipe_diameter_in=pipe_diameter_in,
            pipe_roughness_in=pipe_roughness_in,
            kinematic_viscosity_ft2s=nu_ft2s,
            total_k_factor=total_k_factor,
        )

        # Check if pump can overcome static head at zero flow
        shutoff_head = pump_interp(options.flow_min_gpm)
        if shutoff_head < static_head_ft:
            return SolverResult(
                converged=False,
                error_message=(
                    f"Pump shutoff head ({shutoff_head:.1f} ft) is less than "
                    f"static head ({static_head_ft:.1f} ft). "
                    "Pump cannot overcome system."
                ),
                static_head_ft=static_head_ft,
            )

        # Find operating point
        result = find_operating_point(
            pump_curve=pump_interp,
            system_curve=system_func,
            flow_min=options.flow_min_gpm,
            flow_max=options.flow_max_gpm,
            tolerance=options.tolerance,
        )

        if result is None:
            return SolverResult(
                converged=False,
                error_message="Could not find pump-system curve intersection",
                static_head_ft=static_head_ft,
            )

        operating_flow, operating_head = result

        # Calculate detailed results at operating point
        h_loss, velocity, reynolds, friction_f = calculate_pipe_head_loss_fps(
            length_ft=pipe_length_ft,
            diameter_in=pipe_diameter_in,
            roughness_in=pipe_roughness_in,
            flow_gpm=operating_flow,
            kinematic_viscosity_ft2s=nu_ft2s,
            k_factor=total_k_factor,
        )

        # Calculate NPSH available
        npsh_a = calculate_npsh_available(
            atmospheric_pressure_psi=options.atmospheric_pressure_psi,
            suction_head_ft=suction_head_ft,
            suction_losses_ft=suction_losses_ft,
            vapor_pressure_psi=vapor_pressure_psi,
            fluid_specific_gravity=fluid_properties.specific_gravity,
        )

        # Generate curves for visualization
        system_curve = generate_system_curve(
            static_head_ft=static_head_ft,
            pipe_length_ft=pipe_length_ft,
            pipe_diameter_in=pipe_diameter_in,
            pipe_roughness_in=pipe_roughness_in,
            kinematic_viscosity_ft2s=nu_ft2s,
            total_k_factor=total_k_factor,
            flow_min_gpm=options.flow_min_gpm,
            flow_max_gpm=min(options.flow_max_gpm, operating_flow * 1.5),
            num_points=options.num_curve_points,
        )

        # Generate pump curve points
        pump_curve_data = [(float(p.flow), float(p.head)) for p in pump_curve_points]

        return SolverResult(
            converged=True,
            iterations=1,  # Brent's method converges quickly
            operating_flow_gpm=operating_flow,
            operating_head_ft=operating_head,
            system_curve=system_curve,
            pump_curve=pump_curve_data,
            velocity_fps=velocity,
            reynolds_number=reynolds,
            friction_factor=friction_f,
            total_head_loss_ft=h_loss,
            static_head_ft=static_head_ft,
            npsh_available_ft=npsh_a,
        )

    except Exception as e:
        return SolverResult(
            converged=False,
            error_message=f"Solver error: {e!s}",
        )


# =============================================================================
# Convenience Function for Water
# =============================================================================


def solve_water_system(
    pump_curve_points: list[FlowHeadPoint],
    static_head_ft: float,
    pipe_length_ft: float,
    pipe_diameter_in: float,
    pipe_roughness_in: float,
    water_temp_f: float = 68.0,
    total_k_factor: float = 0.0,
    suction_head_ft: float = 0.0,
    suction_losses_ft: float = 0.0,
    options: SimpleSolverOptions | None = None,
) -> SolverResult:
    """
    Convenience function to solve a water pumping system.

    Args:
        pump_curve_points: Pump performance curve points
        static_head_ft: Total static head in feet
        pipe_length_ft: Total pipe length in feet
        pipe_diameter_in: Pipe inner diameter in inches
        pipe_roughness_in: Pipe absolute roughness in inches
        water_temp_f: Water temperature in Fahrenheit (default 68°F)
        total_k_factor: Sum of K-factors for all fittings
        suction_head_ft: Static suction head (positive = flooded)
        suction_losses_ft: Friction losses in suction piping
        options: Solver configuration options

    Returns:
        SolverResult with operating point and detailed results
    """
    # Get water properties at temperature
    fluid = get_water_properties(water_temp_f, "F")

    return solve_pump_pipe_system(
        pump_curve_points=pump_curve_points,
        static_head_ft=static_head_ft,
        pipe_length_ft=pipe_length_ft,
        pipe_diameter_in=pipe_diameter_in,
        pipe_roughness_in=pipe_roughness_in,
        fluid_properties=fluid,
        total_k_factor=total_k_factor,
        suction_head_ft=suction_head_ft,
        suction_losses_ft=suction_losses_ft,
        options=options,
    )


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "SimpleSolverOptions",
    "SolverResult",
    "build_pump_curve_interpolator",
    "build_system_curve_function",
    "calculate_npsh_available",
    "find_operating_point",
    "generate_system_curve",
    "solve_pump_pipe_system",
    "solve_water_system",
]
