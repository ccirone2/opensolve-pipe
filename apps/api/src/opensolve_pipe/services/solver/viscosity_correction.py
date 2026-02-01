"""ANSI/HI 9.6.7 Pump viscosity correction calculations.

This module implements the Hydraulic Institute method for correcting pump
performance when handling fluids more viscous than water. The correction
factors reduce pump head, flow capacity, and efficiency compared to
water-based test curves.

Reference: ANSI/HI 9.6.7 - Effects of Liquid Viscosity on Rotodynamic Pump Performance
"""

from opensolve_pipe.models.pump import FlowEfficiencyPoint, FlowHeadPoint
from opensolve_pipe.models.results import ViscosityCorrectionFactors

# Viscosity threshold in centistokes (cSt)
# Below this value, correction is skipped (water at ~100°F)
VISCOSITY_THRESHOLD_CST = 4.3

# Default pump speed in RPM (standard 4-pole motor at 60 Hz)
DEFAULT_PUMP_SPEED_RPM = 1750.0

# B parameter limits for HI method applicability
B_PARAMETER_MIN = 1.0
B_PARAMETER_MAX = 40.0


def should_apply_correction(viscosity_cst: float) -> bool:
    """Check if viscosity correction should be applied.

    Args:
        viscosity_cst: Kinematic viscosity in centistokes (cSt)

    Returns:
        True if viscosity exceeds the threshold and correction should be applied
    """
    return viscosity_cst > VISCOSITY_THRESHOLD_CST


def calculate_viscosity_parameter_b(
    flow_bep_gpm: float,
    head_bep_ft: float,
    viscosity_cst: float,
    speed_rpm: float = DEFAULT_PUMP_SPEED_RPM,
) -> float:
    """Calculate the viscosity parameter B per ANSI/HI 9.6.7.

    The B parameter is a dimensionless quantity that characterizes the
    relative effect of viscosity on pump performance.

    Formula: B = 16.5 * (nu^0.5 * H_BEP^0.0625) / (Q_BEP^0.375 * N^0.25)

    Args:
        flow_bep_gpm: Flow at Best Efficiency Point in GPM
        head_bep_ft: Head at Best Efficiency Point in feet
        viscosity_cst: Kinematic viscosity in centistokes (cSt)
        speed_rpm: Pump speed in RPM (default 1750)

    Returns:
        Viscosity parameter B (dimensionless)

    Raises:
        ValueError: If any input is non-positive
    """
    if flow_bep_gpm <= 0:
        raise ValueError("BEP flow must be positive")
    if head_bep_ft <= 0:
        raise ValueError("BEP head must be positive")
    if viscosity_cst <= 0:
        raise ValueError("Viscosity must be positive")
    if speed_rpm <= 0:
        raise ValueError("Pump speed must be positive")

    # B = 16.5 * (nu^0.5 * H_BEP^0.0625) / (Q_BEP^0.375 * N^0.25)
    numerator = (viscosity_cst**0.5) * (head_bep_ft**0.0625)
    denominator = (flow_bep_gpm**0.375) * (speed_rpm**0.25)

    b_parameter: float = 16.5 * numerator / denominator
    return b_parameter


def calculate_correction_factors(b_parameter: float) -> ViscosityCorrectionFactors:
    """Calculate correction factors C_Q, C_H, C_eta from viscosity parameter B.

    Per ANSI/HI 9.6.7:
    - C_Q = 1.0 - 4.5 * 10^-3 * B^1.5  (flow correction)
    - C_H = 1.0 - 7.0 * 10^-4 * B^2.0  (head correction at BEP)
    - C_eta = B^(-0.0547 * B^0.69)       (efficiency correction)

    All factors are clamped to [0, 1] range.

    Args:
        b_parameter: Viscosity parameter B from calculate_viscosity_parameter_b

    Returns:
        ViscosityCorrectionFactors with c_q, c_h, c_eta values
    """
    # Flow correction factor
    c_q = 1.0 - 4.5e-3 * (b_parameter**1.5)
    c_q = max(0.0, min(1.0, c_q))

    # Head correction factor
    c_h = 1.0 - 7.0e-4 * (b_parameter**2.0)
    c_h = max(0.0, min(1.0, c_h))

    # Efficiency correction factor
    # For B close to 0, this approaches 1.0
    # For B = 1.0, C_eta = 1^(-0.0547 * 1^0.69) = 1^(-0.0547) = 1.0
    if b_parameter <= 0:
        c_eta = 1.0
    else:
        exponent = -0.0547 * (b_parameter**0.69)
        c_eta = b_parameter**exponent
        c_eta = max(0.0, min(1.0, c_eta))

    return ViscosityCorrectionFactors(c_q=c_q, c_h=c_h, c_eta=c_eta)


def estimate_bep_from_curve(
    pump_curve_points: list[FlowHeadPoint],
    efficiency_points: list[FlowEfficiencyPoint] | None = None,
) -> tuple[float, float]:
    """Estimate Best Efficiency Point (BEP) flow and head from pump curve.

    If efficiency curve is provided, BEP is at maximum efficiency.
    If not, BEP is estimated at 80% of shutoff head (industry practice).

    Args:
        pump_curve_points: List of flow-head points on the pump curve
        efficiency_points: Optional efficiency curve points

    Returns:
        Tuple of (bep_flow_gpm, bep_head_ft)

    Raises:
        ValueError: If pump curve is empty
    """
    if not pump_curve_points:
        raise ValueError("Pump curve must have at least one point")

    # Sort by flow to ensure proper ordering
    sorted_points = sorted(pump_curve_points, key=lambda p: p.flow)

    if efficiency_points and len(efficiency_points) >= 2:
        # Find maximum efficiency point
        max_eff_point = max(efficiency_points, key=lambda p: p.efficiency)
        bep_flow = max_eff_point.flow

        # Interpolate head at BEP flow from pump curve
        bep_head = _interpolate_head_at_flow(sorted_points, bep_flow)
        return (bep_flow, bep_head)

    # No efficiency curve - estimate BEP at 80% of shutoff head
    # Shutoff head is head at zero flow (first point if curve starts at 0)
    shutoff_head = sorted_points[0].head
    target_head = 0.8 * shutoff_head

    # Find flow at target head (reverse interpolation)
    bep_flow = _interpolate_flow_at_head(sorted_points, target_head)
    return (bep_flow, target_head)


def _interpolate_head_at_flow(sorted_points: list[FlowHeadPoint], flow: float) -> float:
    """Linearly interpolate head at a given flow from pump curve points."""
    if flow <= sorted_points[0].flow:
        return sorted_points[0].head
    if flow >= sorted_points[-1].flow:
        return sorted_points[-1].head

    for i in range(len(sorted_points) - 1):
        if sorted_points[i].flow <= flow <= sorted_points[i + 1].flow:
            # Linear interpolation
            f1, h1 = sorted_points[i].flow, sorted_points[i].head
            f2, h2 = sorted_points[i + 1].flow, sorted_points[i + 1].head
            if f2 == f1:
                return h1
            ratio = (flow - f1) / (f2 - f1)
            return h1 + ratio * (h2 - h1)

    return sorted_points[-1].head


def _interpolate_flow_at_head(sorted_points: list[FlowHeadPoint], head: float) -> float:
    """Find flow at a given head by reverse interpolation.

    Pump curves typically decrease in head as flow increases.
    """
    # Check bounds
    if head >= sorted_points[0].head:
        return sorted_points[0].flow
    if head <= sorted_points[-1].head:
        return sorted_points[-1].flow

    for i in range(len(sorted_points) - 1):
        h1, h2 = sorted_points[i].head, sorted_points[i + 1].head
        f1, f2 = sorted_points[i].flow, sorted_points[i + 1].flow

        # Check if target head is between these points
        # Note: head typically decreases as flow increases
        if (h1 >= head >= h2) or (h2 >= head >= h1):
            if h2 == h1:
                return f1
            ratio = (head - h1) / (h2 - h1)
            return f1 + ratio * (f2 - f1)

    return sorted_points[-1].flow


def apply_viscosity_correction(
    pump_curve_points: list[FlowHeadPoint],
    correction_factors: ViscosityCorrectionFactors,
) -> list[FlowHeadPoint]:
    """Apply viscosity correction to pump curve points.

    Corrected values:
    - Q_viscous = Q_water * C_Q
    - H_viscous = H_water * C_H

    Args:
        pump_curve_points: Original pump curve points (from water test)
        correction_factors: Correction factors from calculate_correction_factors

    Returns:
        New list of corrected FlowHeadPoint objects
    """
    corrected_points = []
    for point in pump_curve_points:
        corrected_flow = point.flow * correction_factors.c_q
        corrected_head = point.head * correction_factors.c_h
        corrected_points.append(FlowHeadPoint(flow=corrected_flow, head=corrected_head))
    return corrected_points


def apply_efficiency_correction(
    efficiency_points: list[FlowEfficiencyPoint],
    correction_factors: ViscosityCorrectionFactors,
) -> list[FlowEfficiencyPoint]:
    """Apply viscosity correction to efficiency curve points.

    Corrected values:
    - Q_viscous = Q_water * C_Q  (flow also corrected)
    - eta_viscous = eta_water * C_eta

    Args:
        efficiency_points: Original efficiency curve points
        correction_factors: Correction factors from calculate_correction_factors

    Returns:
        New list of corrected FlowEfficiencyPoint objects
    """
    corrected_points = []
    for point in efficiency_points:
        corrected_flow = point.flow * correction_factors.c_q
        corrected_efficiency = point.efficiency * correction_factors.c_eta
        # Efficiency must stay in [0, 1]
        corrected_efficiency = max(0.0, min(1.0, corrected_efficiency))
        corrected_points.append(
            FlowEfficiencyPoint(flow=corrected_flow, efficiency=corrected_efficiency)
        )
    return corrected_points


def is_b_parameter_in_range(b_parameter: float) -> bool:
    """Check if B parameter is within HI method applicability limits.

    Args:
        b_parameter: Viscosity parameter B

    Returns:
        True if B is within recommended range [1, 40]
    """
    return B_PARAMETER_MIN <= b_parameter <= B_PARAMETER_MAX


def calculate_corrected_power_hp(
    flow_gpm: float,
    head_ft: float,
    efficiency: float,
    specific_gravity: float = 1.0,
) -> float:
    """Calculate pump power consumption in horsepower.

    Formula: P = (Q * H * SG) / (3960 * eta)

    Args:
        flow_gpm: Flow rate in GPM
        head_ft: Head in feet
        efficiency: Pump efficiency (0-1)
        specific_gravity: Fluid specific gravity (default 1.0 for water)

    Returns:
        Power consumption in horsepower

    Raises:
        ValueError: If efficiency is zero or negative
    """
    if efficiency <= 0:
        raise ValueError("Efficiency must be positive")
    if flow_gpm < 0 or head_ft < 0:
        raise ValueError("Flow and head must be non-negative")

    # 3960 is the constant for GPM, ft, and HP units
    power_hp = (flow_gpm * head_ft * specific_gravity) / (3960.0 * efficiency)
    return power_hp
