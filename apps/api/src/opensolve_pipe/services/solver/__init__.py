"""Simple solver package for single-path hydraulic networks.

This package provides hydraulic calculations for pipe networks including:
- Friction factor calculation (Colebrook equation)
- Darcy-Weisbach head loss
- K-factor resolution for fittings
- System curve generation
- Pump curve interpolation
- Operating point determination
- NPSH calculations
"""

from __future__ import annotations

# Friction calculations
from .friction import (
    FT_TO_M,
    G_FT_S2,
    G_M_S2,
    GPM_TO_CFS,
    GPM_TO_M3S,
    IN_TO_FT,
    IN_TO_M,
    RE_LAMINAR,
    RE_TURBULENT,
    calculate_friction_factor,
    calculate_friction_factor_laminar,
    calculate_friction_head_loss,
    calculate_minor_head_loss,
    calculate_pipe_head_loss_fps,
    calculate_reynolds,
    calculate_total_head_loss,
    calculate_velocity,
    calculate_velocity_fps,
)

# K-factor resolution
from .k_factors import (
    get_f_t,
    get_fitting_k_by_type,
    k_ball_valve,
    k_check_valve_swing,
    k_elbow_45,
    k_elbow_90_lr,
    k_elbow_90_sr,
    k_entrance_rounded,
    k_entrance_sharp,
    k_exit,
    k_gate_valve,
    resolve_fitting_k,
    resolve_fittings_total_k,
)

# Simple solver
from .simple import (
    SimpleSolverOptions,
    SolverResult,
    build_pump_curve_interpolator,
    calculate_npsh_available,
    find_operating_point,
    generate_system_curve,
    solve_pump_pipe_system,
    solve_water_system,
)

__all__ = [
    # Constants
    "FT_TO_M",
    "GPM_TO_CFS",
    "GPM_TO_M3S",
    "G_FT_S2",
    "G_M_S2",
    "IN_TO_FT",
    "IN_TO_M",
    "RE_LAMINAR",
    "RE_TURBULENT",
    # Simple solver
    "SimpleSolverOptions",
    "SolverResult",
    "build_pump_curve_interpolator",
    # Friction calculations
    "calculate_friction_factor",
    "calculate_friction_factor_laminar",
    "calculate_friction_head_loss",
    "calculate_minor_head_loss",
    "calculate_npsh_available",
    "calculate_pipe_head_loss_fps",
    "calculate_reynolds",
    "calculate_total_head_loss",
    "calculate_velocity",
    "calculate_velocity_fps",
    "find_operating_point",
    "generate_system_curve",
    # K-factor resolution
    "get_f_t",
    "get_fitting_k_by_type",
    "k_ball_valve",
    "k_check_valve_swing",
    "k_elbow_45",
    "k_elbow_90_lr",
    "k_elbow_90_sr",
    "k_entrance_rounded",
    "k_entrance_sharp",
    "k_exit",
    "k_gate_valve",
    "resolve_fitting_k",
    "resolve_fittings_total_k",
    "solve_pump_pipe_system",
    "solve_water_system",
]
