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

from .epanet import (
    WNTRBuildContext,
    build_wntr_network,
    convert_wntr_results,
    run_epanet_simulation,
    solve_with_epanet,
)

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
    get_valve_k_factor,
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

# Network solver
from .network import (
    NetworkGraph,
    NetworkType,
    SolverState,
    build_network_graph,
    classify_network,
    solve_project,
)

# Solver registry and strategies
from .registry import SolverRegistry, create_default_registry, default_registry

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
from .strategies import BranchingSolver, LoopedSolver, SimpleSolver

__all__ = [
    "FT_TO_M",
    "GPM_TO_CFS",
    "GPM_TO_M3S",
    "G_FT_S2",
    "G_M_S2",
    "IN_TO_FT",
    "IN_TO_M",
    "RE_LAMINAR",
    "RE_TURBULENT",
    "BranchingSolver",
    "LoopedSolver",
    "NetworkGraph",
    "NetworkType",
    "SimpleSolver",
    "SimpleSolverOptions",
    "SolverRegistry",
    "SolverResult",
    "SolverState",
    "WNTRBuildContext",
    "build_network_graph",
    "build_pump_curve_interpolator",
    "build_wntr_network",
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
    "classify_network",
    "convert_wntr_results",
    "create_default_registry",
    "default_registry",
    "find_operating_point",
    "generate_system_curve",
    "get_f_t",
    "get_fitting_k_by_type",
    "get_valve_k_factor",
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
    "run_epanet_simulation",
    "solve_project",
    "solve_pump_pipe_system",
    "solve_water_system",
    "solve_with_epanet",
    "solve_with_epanet",
]
