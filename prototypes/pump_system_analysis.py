#!/usr/bin/env python3
"""
Pump System Curve Analysis Tool
===============================
Calculates system curves for different pipe sizes and finds operating points
on a pump curve. Uses the fluids library for hydraulic calculations.

Author: [Your Name]
Date: [Date]

Units: Imperial (ft, GPM, inches)
"""

import numpy as np
import matplotlib.pyplot as plt
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from scipy.interpolate import interp1d
from scipy.optimize import brentq

# Import fluids library components
from fluids.friction import friction_factor
from fluids.fittings import bend_rounded


# =============================================================================
# CONFIGURATION - EDIT THIS SECTION
# =============================================================================

# --- Pump Curve Data ---
# Format: List of (Flow_GPM, Head_ft) tuples
# UPDATE THESE VALUES with your actual pump curve data
PUMP_CURVE_DATA: List[Tuple[float, float]] = [
    (0, 120),      # Shutoff head
    (50, 118),
    (100, 115),
    (150, 110),
    (200, 102),
    (250, 92),
    (300, 80),
    (350, 65),
    (400, 48),
    (450, 28),
    (500, 5),      # Runout
]

# --- System Elevations (ft) ---
RESERVOIR_WATER_LEVEL_MIN = 0.0    # Minimum water level in tank (ft above tank base)
RESERVOIR_WATER_LEVEL_MAX = 30.0   # Maximum water level in tank (ft above tank base)
RESERVOIR_WATER_LEVEL_TYPICAL = 15.0  # Typical operating level for calculations
# NOTE: For worst-case pump sizing, use lowest expected level (highest static head)
TANK_BASE_ELEVATION = 0.0         # Tank base elevation (ft)
PUMP_SUCTION_ELEVATION = 1.0      # Pump suction centerline (ft)
PUMP_DISCHARGE_ELEVATION = 1.0    # Pump discharge centerline (ft) - assumed same as suction
DISCHARGE_POINT_ELEVATION = 6.0   # Final discharge elevation (ft)

# --- Pipe Material Properties ---
# Schedule 40 Stainless Steel, new condition
# Roughness values in feet
PIPE_ROUGHNESS_FT = 0.00015  # New stainless steel (~0.0018 inches = 0.00015 ft)

# --- Fluid Properties ---
FLUID_DENSITY = 62.4          # Water density (lb/ft³)
FLUID_VISCOSITY = 0.00001076  # Water kinematic viscosity at 68°F (ft²/s)
GRAVITY = 32.174              # Acceleration due to gravity (ft/s²)

# --- Flow Range for Analysis ---
FLOW_MIN_GPM = 0.0
FLOW_MAX_GPM = 500.0
FLOW_POINTS = 51  # Number of points to calculate


# =============================================================================
# PIPE CONFIGURATIONS
# =============================================================================

@dataclass
class PipeSection:
    """Defines a section of pipe with its properties."""
    name: str
    nominal_diameter_in: float  # Nominal pipe size (inches)
    length_ft: float            # Pipe length (feet)
    
    # Calculated properties (filled in during initialization)
    inner_diameter_ft: float = field(init=False)
    inner_diameter_in: float = field(init=False)
    area_ft2: float = field(init=False)
    
    def __post_init__(self):
        """Calculate derived properties from nominal diameter."""
        # Schedule 40 pipe inner diameters (inches)
        # Reference: ASME B36.10M
        schedule_40_id = {
            2.5: 2.469,
            3.0: 3.068,
            4.0: 4.026,
            6.0: 6.065,
            8.0: 7.981,
        }
        
        if self.nominal_diameter_in in schedule_40_id:
            self.inner_diameter_in = schedule_40_id[self.nominal_diameter_in]
        else:
            # Approximate for other sizes
            self.inner_diameter_in = self.nominal_diameter_in * 0.95
            
        self.inner_diameter_ft = self.inner_diameter_in / 12.0
        self.area_ft2 = np.pi * (self.inner_diameter_ft / 2) ** 2


@dataclass 
class Fitting:
    """Represents a pipe fitting with its K-factor or equivalent length."""
    name: str
    quantity: int
    k_factor: Optional[float] = None  # Direct K-factor if known
    equivalent_length_diameters: Optional[float] = None  # L/D for calculating K
    
    def get_k_factor(self, pipe_diameter_in: float, friction_factor: float) -> float:
        """
        Calculate total K-factor for this fitting type.
        
        Args:
            pipe_diameter_in: Pipe inner diameter in inches
            friction_factor: Darcy friction factor for the pipe
            
        Returns:
            Total K-factor for all fittings of this type
        """
        if self.k_factor is not None:
            return self.k_factor * self.quantity
        elif self.equivalent_length_diameters is not None:
            # K = f * (L/D)
            k_single = friction_factor * self.equivalent_length_diameters
            return k_single * self.quantity
        else:
            return 0.0


@dataclass
class PipingSystem:
    """
    Defines a complete piping system section (suction or discharge).
    
    This class is designed to be easily maintainable - just add or remove
    fittings from the fittings list as the design evolves.
    """
    name: str
    pipe: PipeSection
    fittings: List[Fitting] = field(default_factory=list)
    
    def calculate_k_total(self, friction_factor: float) -> float:
        """Calculate total K-factor for all fittings in this system."""
        return sum(f.get_k_factor(self.pipe.inner_diameter_in, friction_factor) 
                   for f in self.fittings)
    
    def calculate_friction_head_loss(self, flow_gpm: float, roughness_ft: float) -> float:
        """
        Calculate total head loss (friction + fittings) for this piping system.
        
        Args:
            flow_gpm: Flow rate in GPM
            roughness_ft: Pipe roughness in feet
            
        Returns:
            Head loss in feet
        """
        if flow_gpm <= 0:
            return 0.0
            
        # Convert flow to ft³/s
        flow_cfs = flow_gpm / 448.831
        
        # Calculate velocity
        velocity_fps = flow_cfs / self.pipe.area_ft2
        
        # Calculate Reynolds number
        Re = velocity_fps * self.pipe.inner_diameter_ft / FLUID_VISCOSITY
        
        # Calculate friction factor using Colebrook equation
        relative_roughness = roughness_ft / self.pipe.inner_diameter_ft
        
        try:
            f = friction_factor(Re=Re, eD=relative_roughness)
        except:
            # Fallback for very low Reynolds numbers
            f = 64 / Re if Re > 0 else 0.02
        
        # Darcy-Weisbach head loss for pipe
        h_pipe = f * (self.pipe.length_ft / self.pipe.inner_diameter_ft) * \
                 (velocity_fps ** 2) / (2 * GRAVITY)
        
        # Head loss for fittings
        k_total = self.calculate_k_total(f)
        h_fittings = k_total * (velocity_fps ** 2) / (2 * GRAVITY)
        
        return h_pipe + h_fittings
    
    def get_velocity(self, flow_gpm: float) -> float:
        """Calculate velocity in ft/s for given flow rate."""
        if flow_gpm <= 0:
            return 0.0
        flow_cfs = flow_gpm / 448.831
        return flow_cfs / self.pipe.area_ft2


# =============================================================================
# SUCTION SIDE CONFIGURATION
# =============================================================================

def create_suction_system() -> PipingSystem:
    """
    Create the suction side piping system.
    
    Suction side is fixed at 4" Schedule 40 SS.
    Modify the fittings list as the design evolves.
    """
    suction_pipe = PipeSection(
        name="Suction Pipe",
        nominal_diameter_in=4.0,
        length_ft=200.0
    )
    
    # --- SUCTION FITTINGS - UPDATE AS NEEDED ---
    # K-factors and L/D values from Crane TP-410 and fluids library
    suction_fittings = [
        # 90° Long-radius elbows (L/D ≈ 20 for LR elbow)
        Fitting(name="90° Elbow (LR)", quantity=6, equivalent_length_diameters=20),
        
        # Gate valve, fully open (L/D ≈ 8)
        Fitting(name="Gate Valve", quantity=1, equivalent_length_diameters=8),
        
        # Basket strainer (estimated K ≈ 2.0 for clean strainer)
        # UPDATE this value when actual strainer data is available
        Fitting(name="Basket Strainer", quantity=1, k_factor=2.0),
        
        # Pipe entrance from tank (sharp-edged, K ≈ 0.5)
        Fitting(name="Pipe Entrance", quantity=1, k_factor=0.5),
    ]
    
    return PipingSystem(
        name="Suction Side",
        pipe=suction_pipe,
        fittings=suction_fittings
    )


# =============================================================================
# DISCHARGE SIDE CONFIGURATIONS
# =============================================================================

def create_discharge_system(nominal_diameter_in: float) -> PipingSystem:
    """
    Create a discharge side piping system for a given pipe diameter.
    
    Args:
        nominal_diameter_in: Nominal pipe diameter in inches (2.5, 3, or 4)
        
    Returns:
        PipingSystem configured for the specified diameter
    """
    discharge_pipe = PipeSection(
        name=f"Discharge Pipe {nominal_diameter_in}\"",
        nominal_diameter_in=nominal_diameter_in,
        length_ft=1000.0  # 1000+ ft discharge run
    )
    
    # --- DISCHARGE FITTINGS - UPDATE AS NEEDED ---
    # K-factors scale with pipe size for some fittings
    discharge_fittings = [
        # 90° Long-radius elbows (L/D ≈ 20)
        Fitting(name="90° Elbow (LR)", quantity=8, equivalent_length_diameters=20),
        
        # Swing check valve (L/D ≈ 50 for swing check)
        Fitting(name="Swing Check Valve", quantity=1, equivalent_length_diameters=50),
        
        # Gate valves, fully open (L/D ≈ 8)
        Fitting(name="Gate Valve", quantity=2, equivalent_length_diameters=8),
        
        # Reducer at pump discharge (4" pump to discharge size)
        # K for sudden contraction depends on area ratio
        # For 2.5" pump discharge connection to various sizes:
        Fitting(name="Pump Discharge Reducer", quantity=1, 
                k_factor=_get_reducer_k(2.5, nominal_diameter_in)),
        
        # Pipe exit (K = 1.0 for discharge to atmosphere/tank)
        Fitting(name="Pipe Exit", quantity=1, k_factor=1.0),
    ]
    
    return PipingSystem(
        name=f"Discharge Side ({nominal_diameter_in}\")",
        pipe=discharge_pipe,
        fittings=discharge_fittings
    )


def _get_reducer_k(inlet_diameter_in: float, outlet_diameter_in: float) -> float:
    """
    Calculate K-factor for a reducer/expander.
    
    For gradual reducer: K ≈ 0.04 to 0.1
    For sudden contraction: K = 0.5 * (1 - (d/D)²)
    For sudden expansion: K = (1 - (d/D)²)²
    
    Using gradual reducer assumption.
    """
    if abs(inlet_diameter_in - outlet_diameter_in) < 0.1:
        return 0.0  # Same size, no reducer needed
    
    # Gradual reducer/expander
    area_ratio = (min(inlet_diameter_in, outlet_diameter_in) / 
                  max(inlet_diameter_in, outlet_diameter_in)) ** 2
    
    if outlet_diameter_in > inlet_diameter_in:
        # Expansion (pump discharge to larger pipe)
        return 0.1 * (1 - area_ratio)
    else:
        # Contraction (larger pipe to smaller)
        return 0.04 * (1 - area_ratio)


# =============================================================================
# SYSTEM CURVE CALCULATIONS
# =============================================================================

def calculate_static_head(reservoir_level_ft: float) -> float:
    """
    Calculate the static head the pump must overcome.
    
    Static head = (Discharge elevation) - (Suction water surface elevation)
    
    Args:
        reservoir_level_ft: Water level in reservoir (ft above tank base)
        
    Returns:
        Static head in feet
    """
    suction_surface_elevation = TANK_BASE_ELEVATION + reservoir_level_ft
    return DISCHARGE_POINT_ELEVATION - suction_surface_elevation


def calculate_system_head(
    flow_gpm: float,
    suction_system: PipingSystem,
    discharge_system: PipingSystem,
    reservoir_level_ft: float = RESERVOIR_WATER_LEVEL_TYPICAL
) -> float:
    """
    Calculate total system head at a given flow rate.
    
    Total head = Static head + Suction losses + Discharge losses
    
    Args:
        flow_gpm: Flow rate in GPM
        suction_system: Suction side piping system
        discharge_system: Discharge side piping system
        reservoir_level_ft: Water level in reservoir
        
    Returns:
        Total system head in feet
    """
    # Static head
    h_static = calculate_static_head(reservoir_level_ft)
    
    # Friction losses
    h_suction = suction_system.calculate_friction_head_loss(flow_gpm, PIPE_ROUGHNESS_FT)
    h_discharge = discharge_system.calculate_friction_head_loss(flow_gpm, PIPE_ROUGHNESS_FT)
    
    return h_static + h_suction + h_discharge


def generate_system_curve(
    suction_system: PipingSystem,
    discharge_system: PipingSystem,
    reservoir_level_ft: float = RESERVOIR_WATER_LEVEL_TYPICAL,
    flow_range: Tuple[float, float] = (FLOW_MIN_GPM, FLOW_MAX_GPM),
    num_points: int = FLOW_POINTS
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generate system curve data points.
    
    Args:
        suction_system: Suction side configuration
        discharge_system: Discharge side configuration
        reservoir_level_ft: Water level in reservoir
        flow_range: (min_flow, max_flow) in GPM
        num_points: Number of points to calculate
        
    Returns:
        Tuple of (flow_array, head_array) in GPM and feet
    """
    flows = np.linspace(flow_range[0], flow_range[1], num_points)
    heads = np.array([
        calculate_system_head(q, suction_system, discharge_system, reservoir_level_ft)
        for q in flows
    ])
    
    return flows, heads


# =============================================================================
# PUMP CURVE AND OPERATING POINT
# =============================================================================

def create_pump_curve_interpolator(pump_data: List[Tuple[float, float]]) -> interp1d:
    """
    Create an interpolation function for the pump curve.
    
    Args:
        pump_data: List of (flow_GPM, head_ft) tuples
        
    Returns:
        Interpolation function: head = f(flow)
    """
    flows = np.array([p[0] for p in pump_data])
    heads = np.array([p[1] for p in pump_data])
    
    return interp1d(flows, heads, kind='cubic', fill_value='extrapolate')


def find_operating_point(
    pump_curve: interp1d,
    suction_system: PipingSystem,
    discharge_system: PipingSystem,
    reservoir_level_ft: float = RESERVOIR_WATER_LEVEL_TYPICAL,
    flow_range: Tuple[float, float] = (1.0, FLOW_MAX_GPM)
) -> Optional[Tuple[float, float]]:
    """
    Find the operating point where pump curve intersects system curve.
    
    Args:
        pump_curve: Interpolated pump curve function
        suction_system: Suction side configuration
        discharge_system: Discharge side configuration
        reservoir_level_ft: Water level in reservoir
        flow_range: Search range for operating point
        
    Returns:
        Tuple of (flow_GPM, head_ft) at operating point, or None if not found
    """
    def difference(flow):
        pump_head = pump_curve(flow)
        system_head = calculate_system_head(
            flow, suction_system, discharge_system, reservoir_level_ft
        )
        return pump_head - system_head
    
    try:
        # Find where pump head = system head
        flow_op = brentq(difference, flow_range[0], flow_range[1])
        head_op = float(pump_curve(flow_op))
        return (flow_op, head_op)
    except ValueError:
        # No intersection found in range
        return None


# =============================================================================
# REPORTING AND VISUALIZATION
# =============================================================================

def print_system_summary(
    suction_system: PipingSystem,
    discharge_systems: List[PipingSystem],
    pump_curve: interp1d,
    reservoir_level_ft: float = RESERVOIR_WATER_LEVEL_TYPICAL
):
    """Print a summary of the system configuration and operating points."""
    
    print("=" * 70)
    print("PUMP SYSTEM ANALYSIS SUMMARY")
    print("=" * 70)
    
    # Static head
    h_static = calculate_static_head(reservoir_level_ft)
    print(f"\nReservoir water level: {reservoir_level_ft:.1f} ft")
    print(f"Static head: {h_static:.2f} ft")
    
    # Suction system
    print(f"\n--- {suction_system.name} ---")
    print(f"Pipe: {suction_system.pipe.nominal_diameter_in}\" Sch 40 SS")
    print(f"Length: {suction_system.pipe.length_ft:.0f} ft")
    print(f"ID: {suction_system.pipe.inner_diameter_in:.3f} in")
    print("Fittings:")
    for f in suction_system.fittings:
        print(f"  - {f.quantity}x {f.name}")
    
    # Operating points table
    print("\n" + "=" * 70)
    print("OPERATING POINTS")
    print("=" * 70)
    print(f"{'Discharge Size':<16} {'Flow (GPM)':<12} {'Head (ft)':<12} "
          f"{'Velocity (ft/s)':<16} {'Status'}")
    print("-" * 70)
    
    for discharge_system in discharge_systems:
        op = find_operating_point(
            pump_curve, suction_system, discharge_system, reservoir_level_ft
        )
        
        if op:
            flow, head = op
            velocity = discharge_system.get_velocity(flow)
            
            # Check velocity (typical range: 3-10 ft/s for discharge)
            if velocity < 3:
                status = "Low velocity"
            elif velocity > 10:
                status = "High velocity!"
            else:
                status = "OK"
                
            print(f"{discharge_system.pipe.nominal_diameter_in:>6.1f}\"{'':10}"
                  f"{flow:>10.1f}  {head:>10.1f}  {velocity:>14.2f}  {status}")
        else:
            print(f"{discharge_system.pipe.nominal_diameter_in:>6.1f}\"{'':10}"
                  f"{'N/A':>10}  {'N/A':>10}  {'N/A':>14}  No intersection")
    
    print("-" * 70)
    print("\nNotes:")
    print("- Recommended discharge velocity: 3-10 ft/s")
    print("- Recommended suction velocity: 1-5 ft/s")


def plot_curves(
    suction_system: PipingSystem,
    discharge_systems: List[PipingSystem],
    pump_curve: interp1d,
    pump_data: List[Tuple[float, float]],
    reservoir_level_ft: float = RESERVOIR_WATER_LEVEL_TYPICAL,
    save_path: Optional[str] = None
):
    """
    Create a plot showing pump curve vs system curves.
    
    Args:
        suction_system: Suction side configuration
        discharge_systems: List of discharge configurations to compare
        pump_curve: Interpolated pump curve function
        pump_data: Original pump curve data points
        reservoir_level_ft: Water level for calculations
        save_path: Path to save the figure (optional)
    """
    fig, ax = plt.subplots(figsize=(12, 8))
    
    flows = np.linspace(FLOW_MIN_GPM, FLOW_MAX_GPM, 100)
    
    # Plot pump curve
    pump_flows = np.array([p[0] for p in pump_data])
    pump_heads = np.array([p[1] for p in pump_data])
    ax.plot(pump_flows, pump_heads, 'ko', markersize=8, label='Pump Curve Data')
    ax.plot(flows, pump_curve(flows), 'k-', linewidth=2.5, label='Pump Curve')
    
    # Colors for different pipe sizes
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
    
    # Plot system curves and operating points
    for i, discharge_system in enumerate(discharge_systems):
        color = colors[i % len(colors)]
        
        # Generate system curve
        sys_flows, sys_heads = generate_system_curve(
            suction_system, discharge_system, reservoir_level_ft
        )
        
        label = f'System Curve - {discharge_system.pipe.nominal_diameter_in}" Discharge'
        ax.plot(sys_flows, sys_heads, '-', color=color, linewidth=2, label=label)
        
        # Find and mark operating point
        op = find_operating_point(
            pump_curve, suction_system, discharge_system, reservoir_level_ft
        )
        
        if op:
            flow_op, head_op = op
            ax.plot(flow_op, head_op, 'o', color=color, markersize=12, 
                    markeredgecolor='black', markeredgewidth=2,
                    label=f'Operating Point ({flow_op:.0f} GPM, {head_op:.1f} ft)')
    
    # Static head line
    h_static = calculate_static_head(reservoir_level_ft)
    ax.axhline(y=h_static, color='gray', linestyle='--', linewidth=1,
               label=f'Static Head ({h_static:.1f} ft)')
    
    # Formatting
    ax.set_xlabel('Flow Rate (GPM)', fontsize=12)
    ax.set_ylabel('Head (ft)', fontsize=12)
    ax.set_title(f'Pump Curve vs System Curves\n'
                 f'(Reservoir Level: {reservoir_level_ft:.0f} ft)', fontsize=14)
    ax.set_xlim(FLOW_MIN_GPM, FLOW_MAX_GPM)
    ax.set_ylim(0, max(pump_heads) * 1.1)
    ax.grid(True, alpha=0.3)
    ax.legend(loc='upper right', fontsize=9)
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"\nPlot saved to: {save_path}")
    
    plt.show()
    
    return fig


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main():
    """Main function to run the analysis."""
    
    print("\n" + "=" * 70)
    print("PUMP SYSTEM CURVE ANALYSIS")
    print("=" * 70)
    
    # Create pump curve interpolator
    pump_curve = create_pump_curve_interpolator(PUMP_CURVE_DATA)
    
    # Create suction system (fixed at 4")
    suction_system = create_suction_system()
    
    # Create discharge systems for different pipe sizes
    discharge_sizes = [2.5, 3.0, 4.0]  # inches
    discharge_systems = [create_discharge_system(size) for size in discharge_sizes]
    
    # Print summary
    print_system_summary(
        suction_system, 
        discharge_systems, 
        pump_curve,
        reservoir_level_ft=RESERVOIR_WATER_LEVEL_TYPICAL
    )
    
    # Generate plot
    fig = plot_curves(
        suction_system,
        discharge_systems,
        pump_curve,
        PUMP_CURVE_DATA,
        reservoir_level_ft=RESERVOIR_WATER_LEVEL_TYPICAL,
        save_path='/home/claude/pump_system_curves.png'
    )
    
    # Optional: Show effect of different reservoir levels
    print("\n" + "=" * 70)
    print("SENSITIVITY ANALYSIS - RESERVOIR LEVEL EFFECT")
    print("=" * 70)
    print(f"\nUsing 3\" discharge pipe:")
    print(f"{'Reservoir Level (ft)':<22} {'Flow (GPM)':<12} {'Head (ft)':<12}")
    print("-" * 46)
    
    discharge_3in = discharge_systems[1]  # 3" pipe
    for level in [5, 15, 25, 30]:
        op = find_operating_point(
            pump_curve, suction_system, discharge_3in, reservoir_level_ft=level
        )
        if op:
            print(f"{level:>10.0f}{'':12}{op[0]:>10.1f}  {op[1]:>10.1f}")
        else:
            print(f"{level:>10.0f}{'':12}{'N/A':>10}  {'N/A':>10}")
    
    return fig


if __name__ == "__main__":
    main()
