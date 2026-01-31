"""WNTR/EPANET integration for solving looped hydraulic networks.

This module provides a wrapper around WNTR (Water Network Tool for Resilience)
to solve complex hydraulic networks using the EPANET engine. It handles:
- Converting OpenSolve component models to WNTR network elements
- Running the EPANET steady-state simulation
- Converting WNTR results back to OpenSolve's SolvedState format

EPANET is used for looped networks that cannot be solved with the
simple path-based solver (SimpleSolver) or tree-based solver (BranchingSolver).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from time import perf_counter
from typing import TYPE_CHECKING, Any

import wntr
from wntr.network import WaterNetworkModel

from ...models.components import (
    ComponentType,
    HeatExchanger,
    Junction,
    Orifice,
    PumpComponent,
    PumpStatus,
    Reservoir,
    Sprinkler,
    Strainer,
    Tank,
    ValveComponent,
    ValveStatus,
    ValveType,
)
from ...models.plug import Plug
from ...models.pump import FlowHeadPoint
from ...models.reference_node import IdealReferenceNode, NonIdealReferenceNode
from ...models.results import (
    ComponentResult,
    FlowRegime,
    PipingResult,
    PumpResult,
    SolvedState,
    Warning,
    WarningCategory,
    WarningSeverity,
)

if TYPE_CHECKING:
    from ...models.components import Component
    from ...models.connections import PipeConnection
    from ...models.fluids import FluidProperties
    from ...models.project import Project

logger = logging.getLogger(__name__)


# Conversion constants
FT_TO_M = 0.3048
M_TO_FT = 3.28084
GPM_TO_M3S = 6.309e-5
M3S_TO_GPM = 15850.32
PSI_TO_M = 0.703070  # psi to meters of water head
M_TO_PSI = 1.4219702  # meters of water head to psi
IN_TO_M = 0.0254


@dataclass
class WNTRBuildContext:
    """Context for building WNTR network, tracking mappings and state."""

    wn: WaterNetworkModel = field(default_factory=WaterNetworkModel)

    # Mapping from OpenSolve IDs to WNTR element names
    node_map: dict[str, str] = field(default_factory=dict)  # component_id -> wntr_node
    link_map: dict[str, str] = field(default_factory=dict)  # connection_id -> wntr_link
    pump_map: dict[str, str] = field(default_factory=dict)  # pump_id -> wntr_pump

    # Track implicit junctions created for branch components
    implicit_junctions: dict[str, list[str]] = field(
        default_factory=dict
    )  # component_id -> [junction_names]

    # Counter for generating unique names
    junction_counter: int = 0
    pipe_counter: int = 0
    pump_counter: int = 0
    valve_counter: int = 0
    curve_counter: int = 0

    # Warnings collected during build
    warnings: list[Warning] = field(default_factory=list)

    def next_junction_name(self) -> str:
        """Generate unique junction name."""
        self.junction_counter += 1
        return f"J{self.junction_counter}"

    def next_pipe_name(self) -> str:
        """Generate unique pipe name."""
        self.pipe_counter += 1
        return f"P{self.pipe_counter}"

    def next_pump_name(self) -> str:
        """Generate unique pump name."""
        self.pump_counter += 1
        return f"PU{self.pump_counter}"

    def next_valve_name(self) -> str:
        """Generate unique valve name."""
        self.valve_counter += 1
        return f"V{self.valve_counter}"

    def next_curve_name(self) -> str:
        """Generate unique curve name."""
        self.curve_counter += 1
        return f"C{self.curve_counter}"


def build_wntr_network(
    project: Project,
    fluid_props: FluidProperties,
) -> tuple[WNTRBuildContext, list[Warning]]:
    """Build a WNTR network from an OpenSolve project.

    Args:
        project: The OpenSolve project to convert
        fluid_props: Fluid properties for the simulation

    Returns:
        Tuple of (WNTRBuildContext with network, list of warnings)
    """
    ctx = WNTRBuildContext()
    wn = ctx.wn

    # Set network options
    wn.options.time.duration = 0  # Steady-state simulation
    wn.options.hydraulic.demand_model = "DD"  # Demand-driven

    # Add components as nodes
    for comp in project.components:
        _add_component_to_wntr(ctx, comp, project, fluid_props)

    # Add connections as pipes/links
    for conn in project.connections:
        _add_connection_to_wntr(ctx, conn, project, fluid_props)

    return ctx, ctx.warnings


def _add_component_to_wntr(
    ctx: WNTRBuildContext,
    comp: Component,
    project: Project,
    fluid_props: FluidProperties,
) -> None:
    """Add a component to the WNTR network as appropriate node type."""
    wn = ctx.wn

    if isinstance(comp, Reservoir):
        node_name = comp.id
        # WNTR reservoirs use head (elevation + water level), in meters
        total_head_m = (comp.elevation + comp.water_level) * FT_TO_M
        wn.add_reservoir(node_name, base_head=total_head_m)
        ctx.node_map[comp.id] = node_name

    elif isinstance(comp, Tank):
        node_name = comp.id
        # WNTR tanks need elevation, diameter, levels in meters
        wn.add_tank(
            node_name,
            elevation=comp.elevation * FT_TO_M,
            init_level=comp.initial_level * FT_TO_M,
            min_level=comp.min_level * FT_TO_M,
            max_level=comp.max_level * FT_TO_M,
            diameter=comp.diameter * FT_TO_M,
        )
        ctx.node_map[comp.id] = node_name

    elif isinstance(comp, Junction):
        node_name = comp.id
        # Convert demand from GPM to m³/s
        demand_m3s = comp.demand * GPM_TO_M3S
        wn.add_junction(
            node_name,
            base_demand=demand_m3s,
            elevation=comp.elevation * FT_TO_M,
        )
        ctx.node_map[comp.id] = node_name

    elif isinstance(comp, IdealReferenceNode):
        node_name = comp.id
        # Ideal reference node is a reservoir with fixed pressure
        # Convert pressure (psi) to head (m)
        head_m = comp.total_head * FT_TO_M
        wn.add_reservoir(node_name, base_head=head_m)
        ctx.node_map[comp.id] = node_name

    elif isinstance(comp, NonIdealReferenceNode):
        node_name = comp.id
        # Non-ideal reference node has a pressure-flow curve
        # For now, use the first point's pressure as base head
        if comp.pressure_flow_curve:
            base_head_m = comp.pressure_flow_curve[0].pressure * FT_TO_M
        else:
            base_head_m = comp.elevation * FT_TO_M
        wn.add_reservoir(node_name, base_head=base_head_m)
        ctx.node_map[comp.id] = node_name
        # Note: Full pressure-flow curve support would require EPANET's
        # head pattern feature, which is more complex

    elif isinstance(comp, Plug):
        node_name = comp.id
        # Plug is a dead-end junction with zero demand
        wn.add_junction(
            node_name,
            base_demand=0.0,
            elevation=comp.elevation * FT_TO_M,
        )
        ctx.node_map[comp.id] = node_name

    elif isinstance(comp, PumpComponent):
        # Pumps in EPANET are links, not nodes
        # We need to create implicit junction nodes for pump suction/discharge
        suction_name = f"{comp.id}_suction"
        discharge_name = f"{comp.id}_discharge"

        wn.add_junction(
            suction_name,
            base_demand=0.0,
            elevation=comp.elevation * FT_TO_M,
        )
        wn.add_junction(
            discharge_name,
            base_demand=0.0,
            elevation=comp.elevation * FT_TO_M,
        )

        # Get pump curve and add to WNTR
        pump_curve = project.get_pump_curve(comp.curve_id)
        if pump_curve is not None:
            curve_name = ctx.next_curve_name()
            # Convert curve points: GPM -> m³/s, ft -> m
            curve_points = [
                (pt.flow * GPM_TO_M3S, pt.head * FT_TO_M) for pt in pump_curve.points
            ]
            wn.add_curve(curve_name, "HEAD", curve_points)

            # Add pump link
            pump_name = ctx.next_pump_name()
            wn.add_pump(
                pump_name,
                suction_name,
                discharge_name,
                pump_type="HEAD",
                pump_parameter=curve_name,
                speed=comp.speed,
            )
            ctx.pump_map[comp.id] = pump_name

            # Handle pump status
            pump_link = wn.get_link(pump_name)
            if comp.status == PumpStatus.RUNNING:
                # Normal operation - pump is open
                pump_link.initial_status = wntr.network.LinkStatus.Open
            elif comp.status == PumpStatus.OFF_WITH_CHECK:
                # Off with check valve - pump closed, no reverse flow
                pump_link.initial_status = wntr.network.LinkStatus.Closed
            elif comp.status == PumpStatus.OFF_NO_CHECK:
                # Off without check - pump closed, add bypass for reverse flow
                pump_link.initial_status = wntr.network.LinkStatus.Closed
                # Add a low-resistance bypass pipe for potential reverse flow
                bypass_name = ctx.next_pipe_name()
                wn.add_pipe(
                    bypass_name,
                    suction_name,
                    discharge_name,
                    length=0.1,  # Very short pipe
                    diameter=0.01,  # Small diameter (10mm) for low resistance
                    roughness=0.0015,  # Smooth pipe
                    minor_loss=0.5,  # Some minor loss
                )
            elif comp.status == PumpStatus.LOCKED_OUT:
                # Locked out - pump closed, acts as closed valve
                pump_link.initial_status = wntr.network.LinkStatus.Closed
        else:
            ctx.warnings.append(
                Warning(
                    category=WarningCategory.DATA,
                    severity=WarningSeverity.ERROR,
                    component_id=comp.id,
                    message=f"Pump curve '{comp.curve_id}' not found",
                )
            )

        # Map component to both junctions
        ctx.node_map[comp.id] = suction_name  # Primary mapping
        ctx.implicit_junctions[comp.id] = [suction_name, discharge_name]

    elif isinstance(comp, ValveComponent):
        # Control valves (PRV, PSV, FCV) are links in EPANET
        # Regular valves (gate, ball) are modeled as pipes with K-factor loss
        inlet_name = f"{comp.id}_inlet"
        outlet_name = f"{comp.id}_outlet"

        wn.add_junction(
            inlet_name,
            base_demand=0.0,
            elevation=comp.elevation * FT_TO_M,
        )
        wn.add_junction(
            outlet_name,
            base_demand=0.0,
            elevation=comp.elevation * FT_TO_M,
        )

        ctx.node_map[comp.id] = inlet_name
        ctx.implicit_junctions[comp.id] = [inlet_name, outlet_name]

        # Handle valve status: ISOLATED or FAILED_CLOSED = closed valve
        if comp.status in (ValveStatus.ISOLATED, ValveStatus.FAILED_CLOSED):
            # Model as closed valve - very high K-factor
            pipe_name = ctx.next_pipe_name()
            wn.add_pipe(
                pipe_name,
                inlet_name,
                outlet_name,
                length=0.01,
                diameter=0.1,
                roughness=0.0001,
                minor_loss=1e6,  # Essentially closed
            )
            ctx.link_map[comp.id] = pipe_name

        elif comp.valve_type in (ValveType.PRV, ValveType.PSV, ValveType.FCV):
            # Control valve - use WNTR valve
            valve_name = ctx.next_valve_name()

            # Handle FAILED_OPEN and LOCKED_OPEN for control valves
            if comp.status == ValveStatus.FAILED_OPEN:
                # Valve failed open - model as open pipe, no control action
                pipe_name = ctx.next_pipe_name()
                wn.add_pipe(
                    pipe_name,
                    inlet_name,
                    outlet_name,
                    length=0.01,
                    diameter=0.1,
                    roughness=0.0001,
                    minor_loss=0.1,  # Minimal loss for open valve
                )
                ctx.link_map[comp.id] = pipe_name
            elif comp.status == ValveStatus.LOCKED_OPEN:
                # Valve locked at current position - no setpoint control
                # Model as pipe with K-factor based on position
                pipe_name = ctx.next_pipe_name()
                k_factor = _get_valve_k_factor(comp)
                wn.add_pipe(
                    pipe_name,
                    inlet_name,
                    outlet_name,
                    length=0.01,
                    diameter=0.1,
                    roughness=0.0001,
                    minor_loss=k_factor,
                )
                ctx.link_map[comp.id] = pipe_name
            else:  # ACTIVE status - normal control valve operation
                if comp.valve_type == ValveType.PRV:
                    valve_type = "PRV"
                    # Setting is downstream pressure in meters
                    setting = (comp.setpoint or 0.0) * PSI_TO_M
                elif comp.valve_type == ValveType.PSV:
                    valve_type = "PSV"
                    setting = (comp.setpoint or 0.0) * PSI_TO_M
                else:  # FCV
                    valve_type = "FCV"
                    # Setting is flow in m³/s
                    setting = (comp.setpoint or 0.0) * GPM_TO_M3S

                wn.add_valve(
                    valve_name,
                    inlet_name,
                    outlet_name,
                    diameter=0.1,  # 100mm default
                    valve_type=valve_type,
                    minor_loss=0.0,
                    setting=setting,
                )
                ctx.link_map[comp.id] = valve_name
        else:
            # Regular valve - model as short pipe with minor loss
            pipe_name = ctx.next_pipe_name()
            # Get K-factor based on valve type, position, and status
            k_factor = _get_valve_k_factor(comp)
            wn.add_pipe(
                pipe_name,
                inlet_name,
                outlet_name,
                length=0.01,  # Very short pipe
                diameter=0.1,  # 100mm default
                roughness=0.0001,  # Smooth
                minor_loss=k_factor,
            )
            ctx.link_map[comp.id] = pipe_name

    elif comp.type in (
        ComponentType.TEE_BRANCH,
        ComponentType.WYE_BRANCH,
        ComponentType.CROSS_BRANCH,
    ):
        # Branch components need multiple junction nodes for each port
        junction_names = []

        for port in comp.ports:
            junc_name = f"{comp.id}_{port.id}"
            wn.add_junction(
                junc_name,
                base_demand=0.0,
                elevation=comp.elevation * FT_TO_M,
            )
            junction_names.append(junc_name)

        ctx.node_map[comp.id] = junction_names[0] if junction_names else comp.id
        ctx.implicit_junctions[comp.id] = junction_names

        # Connect internal junctions with zero-length pipes
        # (branch K-factors will be handled as minor losses on connecting pipes)
        for i in range(1, len(junction_names)):
            pipe_name = ctx.next_pipe_name()
            wn.add_pipe(
                pipe_name,
                junction_names[0],
                junction_names[i],
                length=0.001,
                diameter=0.1,
                roughness=0.0001,
                minor_loss=0.0,
            )

    elif isinstance(comp, HeatExchanger):
        # Model as junction with implicit pipe for pressure drop
        inlet_name = f"{comp.id}_inlet"
        outlet_name = f"{comp.id}_outlet"

        wn.add_junction(inlet_name, base_demand=0.0, elevation=comp.elevation * FT_TO_M)
        wn.add_junction(
            outlet_name, base_demand=0.0, elevation=comp.elevation * FT_TO_M
        )

        ctx.node_map[comp.id] = inlet_name
        ctx.implicit_junctions[comp.id] = [inlet_name, outlet_name]

        # Add internal pipe with minor loss coefficient
        # K = (dP * 2g) / v² at design flow
        # Approximate K from pressure drop
        k_factor = comp.pressure_drop * 2.0  # Simplified approximation
        pipe_name = ctx.next_pipe_name()
        wn.add_pipe(
            pipe_name,
            inlet_name,
            outlet_name,
            length=0.01,
            diameter=0.1,
            roughness=0.0001,
            minor_loss=k_factor,
        )
        ctx.link_map[comp.id] = pipe_name

    elif isinstance(comp, Strainer):
        inlet_name = f"{comp.id}_inlet"
        outlet_name = f"{comp.id}_outlet"

        wn.add_junction(inlet_name, base_demand=0.0, elevation=comp.elevation * FT_TO_M)
        wn.add_junction(
            outlet_name, base_demand=0.0, elevation=comp.elevation * FT_TO_M
        )

        ctx.node_map[comp.id] = inlet_name
        ctx.implicit_junctions[comp.id] = [inlet_name, outlet_name]

        k_factor = comp.k_factor if comp.k_factor is not None else 2.0
        pipe_name = ctx.next_pipe_name()
        wn.add_pipe(
            pipe_name,
            inlet_name,
            outlet_name,
            length=0.01,
            diameter=0.1,
            roughness=0.0001,
            minor_loss=k_factor,
        )
        ctx.link_map[comp.id] = pipe_name

    elif isinstance(comp, Orifice):
        inlet_name = f"{comp.id}_inlet"
        outlet_name = f"{comp.id}_outlet"

        wn.add_junction(inlet_name, base_demand=0.0, elevation=comp.elevation * FT_TO_M)
        wn.add_junction(
            outlet_name, base_demand=0.0, elevation=comp.elevation * FT_TO_M
        )

        ctx.node_map[comp.id] = inlet_name
        ctx.implicit_junctions[comp.id] = [inlet_name, outlet_name]

        # Orifice K-factor ≈ (1/Cd - 1)² for sharp-edged
        cd = comp.discharge_coefficient
        k_factor = ((1.0 / cd) - 1.0) ** 2 if cd > 0 else 10.0

        pipe_name = ctx.next_pipe_name()
        wn.add_pipe(
            pipe_name,
            inlet_name,
            outlet_name,
            length=0.01,
            diameter=comp.orifice_diameter * IN_TO_M,
            roughness=0.0001,
            minor_loss=k_factor,
        )
        ctx.link_map[comp.id] = pipe_name

    elif isinstance(comp, Sprinkler):
        node_name = comp.id
        # Sprinkler is modeled as junction with emitter coefficient
        # Q = K * sqrt(P), where K is the sprinkler K-factor
        # EPANET emitter coefficient: Q = C * P^n, where n=0.5
        # C = K in appropriate units (m³/s/m^0.5)
        k_gpm_psi = comp.k_factor
        # Convert: 1 GPM/psi^0.5 ≈ 0.0000757 m³/s/m^0.5
        k_m3s_m = k_gpm_psi * 0.0000757

        wn.add_junction(
            node_name,
            base_demand=0.0,
            elevation=comp.elevation * FT_TO_M,
            emitter_coefficient=k_m3s_m,
        )
        ctx.node_map[comp.id] = node_name

    else:
        # Unknown component type - add as simple junction
        node_name = comp.id
        wn.add_junction(
            node_name,
            base_demand=0.0,
            elevation=comp.elevation * FT_TO_M,
        )
        ctx.node_map[comp.id] = node_name
        ctx.warnings.append(
            Warning(
                category=WarningCategory.DATA,
                severity=WarningSeverity.WARNING,
                component_id=comp.id,
                message=f"Unknown component type '{comp.type}' modeled as junction",
            )
        )


def _add_connection_to_wntr(
    ctx: WNTRBuildContext,
    conn: PipeConnection,
    project: Project,
    fluid_props: FluidProperties,
) -> None:
    """Add a pipe connection to the WNTR network."""
    wn = ctx.wn

    # Get start and end node names
    from_comp = next(
        (c for c in project.components if c.id == conn.from_component_id), None
    )
    to_comp = next(
        (c for c in project.components if c.id == conn.to_component_id), None
    )

    if from_comp is None or to_comp is None:
        ctx.warnings.append(
            Warning(
                category=WarningCategory.TOPOLOGY,
                severity=WarningSeverity.ERROR,
                message=f"Connection {conn.id} references missing component",
            )
        )
        return

    # Determine correct junction names based on port IDs
    from_node = _get_wntr_node_for_port(ctx, from_comp, conn.from_port_id, "outlet")
    to_node = _get_wntr_node_for_port(ctx, to_comp, conn.to_port_id, "inlet")

    if from_node is None or to_node is None:
        ctx.warnings.append(
            Warning(
                category=WarningCategory.TOPOLOGY,
                severity=WarningSeverity.ERROR,
                message=f"Could not resolve nodes for connection {conn.id}",
            )
        )
        return

    # Get pipe properties
    if conn.piping and conn.piping.pipe:
        pipe = conn.piping.pipe
        length_m = pipe.length * FT_TO_M
        diameter_m = pipe.nominal_diameter * IN_TO_M

        # Get roughness (convert from inches to meters)
        if pipe.roughness_override is not None:
            roughness_m = pipe.roughness_override * IN_TO_M
        else:
            # Default roughness by material
            roughness_map = {
                "carbon_steel": 0.0018,
                "stainless_steel": 0.00006,
                "pvc": 0.00006,
                "hdpe": 0.00006,
                "copper": 0.00006,
                "cast_iron": 0.01,
                "ductile_iron": 0.01,
            }
            material_key = (
                pipe.material.value
                if hasattr(pipe.material, "value")
                else str(pipe.material)
            )
            roughness_in = roughness_map.get(material_key, 0.0018)
            roughness_m = roughness_in * IN_TO_M

        # Calculate minor loss from fittings
        minor_loss = 0.0
        if conn.piping.fittings:
            from .k_factors import resolve_fittings_total_k

            minor_loss = resolve_fittings_total_k(
                conn.piping.fittings, pipe.nominal_diameter
            )
    else:
        # Default pipe properties if no piping specified
        length_m = 1.0
        diameter_m = 0.1
        roughness_m = 0.000046  # Smooth pipe
        minor_loss = 0.0

    # Add pipe to network
    pipe_name = ctx.next_pipe_name()
    wn.add_pipe(
        pipe_name,
        from_node,
        to_node,
        length=max(length_m, 0.001),  # Minimum length
        diameter=diameter_m,
        roughness=roughness_m,
        minor_loss=minor_loss,
    )
    ctx.link_map[conn.id] = pipe_name


def _get_wntr_node_for_port(
    ctx: WNTRBuildContext,
    comp: Component,
    port_id: str | None,
    direction: str,
) -> str | None:
    """Get the WNTR node name for a component port.

    For multi-port components (pumps, valves, branches), this returns
    the appropriate implicit junction based on port ID and direction.
    """
    # Check for implicit junctions
    if comp.id in ctx.implicit_junctions:
        junctions = ctx.implicit_junctions[comp.id]

        # For pumps: suction (inlet) is first, discharge (outlet) is second
        if comp.type == ComponentType.PUMP:
            if direction == "inlet" or (port_id and "suction" in port_id.lower()):
                return junctions[0] if junctions else None
            else:
                return junctions[1] if len(junctions) > 1 else junctions[0]

        # For valves: inlet first, outlet second
        if comp.type == ComponentType.VALVE:
            if direction == "inlet":
                return junctions[0] if junctions else None
            else:
                return junctions[1] if len(junctions) > 1 else junctions[0]

        # For branches: try to match port ID
        if port_id:
            matching = [j for j in junctions if port_id in j]
            if matching:
                return matching[0]

        # Default to first junction
        return junctions[0] if junctions else None

    # Simple component - use direct mapping
    return ctx.node_map.get(comp.id)


def _get_valve_k_factor(valve: ValveComponent) -> float:
    """Get K-factor for a valve based on type, position, and status."""
    # Handle status first
    if valve.status in (ValveStatus.ISOLATED, ValveStatus.FAILED_CLOSED):
        return 1e6  # Essentially closed

    if valve.status == ValveStatus.FAILED_OPEN:
        # Return minimum K for fully open valve
        base_k = {
            ValveType.GATE: 0.2,
            ValveType.BALL: 0.05,
            ValveType.BUTTERFLY: 0.3,
            ValveType.GLOBE: 4.0,
            ValveType.CHECK: 2.0,
            ValveType.STOP_CHECK: 3.0,
        }
        return base_k.get(valve.valve_type, 1.0)

    # ACTIVE or LOCKED_OPEN: use position-based K-factor
    # Base K-factors for fully open valves (Crane TP-410)
    base_k = {
        ValveType.GATE: 0.2,
        ValveType.BALL: 0.05,
        ValveType.BUTTERFLY: 0.3,
        ValveType.GLOBE: 4.0,
        ValveType.CHECK: 2.0,
        ValveType.STOP_CHECK: 3.0,
    }

    k = base_k.get(valve.valve_type, 1.0)

    # Adjust for position (0 = closed, 1 = open)
    if valve.position is not None:
        if valve.position < 0.01:
            k = 1e6  # Essentially closed
        elif valve.position < 1.0:
            # K increases as valve closes (approximate)
            k = k / (valve.position**2)

    return k


def run_epanet_simulation(
    ctx: WNTRBuildContext,
) -> tuple[Any | None, str | None]:
    """Run EPANET simulation on the WNTR network.

    Args:
        ctx: Build context with WNTR network

    Returns:
        Tuple of (simulation results, error message or None)
    """
    wn = ctx.wn

    try:
        # Use EPANET simulator
        sim = wntr.sim.EpanetSimulator(wn)
        results = sim.run_sim()
        return results, None

    except Exception as e:
        error_msg = str(e)
        logger.error(f"EPANET simulation failed: {error_msg}")

        # Try to provide more helpful error messages
        if "EPANET" in error_msg:
            if "convergence" in error_msg.lower():
                return None, (
                    "EPANET solver failed to converge. "
                    "Check for disconnected components or unrealistic conditions."
                )
            elif "negative" in error_msg.lower():
                return None, (
                    "EPANET detected negative pressures. "
                    "Check pump sizing and system head requirements."
                )

        return None, f"EPANET simulation error: {error_msg}"


def convert_wntr_results(
    ctx: WNTRBuildContext,
    results: Any,
    project: Project,
    fluid_props: FluidProperties,
    start_time: float,
) -> SolvedState:
    """Convert WNTR simulation results to OpenSolve SolvedState.

    Args:
        ctx: Build context with mappings
        results: WNTR simulation results
        project: Original project
        fluid_props: Fluid properties
        start_time: Simulation start time for timing

    Returns:
        SolvedState with converted results
    """
    warnings = list(ctx.warnings)

    # Get results at time 0 (steady-state)
    node_results = results.node
    link_results = results.link

    # Convert node results to ComponentResults
    component_results: dict[str, ComponentResult] = {}

    for comp in project.components:
        # Get the WNTR node name(s) for this component
        if comp.id in ctx.implicit_junctions:
            junctions = ctx.implicit_junctions[comp.id]
        elif comp.id in ctx.node_map:
            junctions = [ctx.node_map[comp.id]]
        else:
            continue

        for wntr_node in junctions:
            try:
                # Get pressure (head) at node - in meters
                head_m = node_results["head"][wntr_node].iloc[0]
                pressure_m = node_results["pressure"][wntr_node].iloc[0]

                # Convert to feet and psi
                head_ft = head_m * M_TO_FT
                pressure_psi = pressure_m * M_TO_PSI

                # Determine port ID from junction name
                if "_" in wntr_node and wntr_node.startswith(comp.id):
                    port_id = wntr_node.replace(f"{comp.id}_", "")
                else:
                    port_id = "default"

                result_key = f"{comp.id}_{port_id}"
                component_results[result_key] = ComponentResult(
                    component_id=comp.id,
                    port_id=port_id,
                    pressure=pressure_psi,
                    dynamic_pressure=0.0,  # Not directly available from EPANET
                    total_pressure=pressure_psi,
                    hgl=head_ft,
                    egl=head_ft,  # Simplified - would need velocity head
                )

            except (KeyError, IndexError) as e:
                logger.warning(f"Could not get results for node {wntr_node}: {e}")

    # Convert link results to PipingResults
    piping_results: dict[str, PipingResult] = {}

    for conn in project.connections:
        if conn.id not in ctx.link_map:
            continue

        wntr_link = ctx.link_map[conn.id]

        try:
            # Get flow (m³/s) and velocity (m/s)
            flow_m3s = link_results["flowrate"][wntr_link].iloc[0]
            velocity_ms = link_results["velocity"][wntr_link].iloc[0]

            # Convert to GPM and ft/s
            flow_gpm = abs(flow_m3s) * M3S_TO_GPM
            velocity_fps = abs(velocity_ms) * M_TO_FT

            # Get head loss if available
            try:
                head_loss_m = abs(link_results["headloss"][wntr_link].iloc[0])
                head_loss_ft = head_loss_m * M_TO_FT
            except KeyError:
                head_loss_ft = 0.0

            # Calculate Reynolds number
            if conn.piping and conn.piping.pipe:
                diameter_ft = conn.piping.pipe.nominal_diameter / 12.0
            else:
                diameter_ft = 0.33  # 4" default

            nu_ft2s = fluid_props.kinematic_viscosity * 10.7639
            reynolds = (velocity_fps * diameter_ft / nu_ft2s) if nu_ft2s > 0 else 0.0

            # Determine flow regime
            if reynolds < 2300:
                regime = FlowRegime.LAMINAR
            elif reynolds < 4000:
                regime = FlowRegime.TRANSITIONAL
            else:
                regime = FlowRegime.TURBULENT

            # Estimate friction factor from Reynolds (simplified)
            if reynolds > 0:
                if reynolds < 2300:
                    friction_f = 64.0 / reynolds
                else:
                    friction_f = 0.316 / (reynolds**0.25)  # Blasius
            else:
                friction_f = 0.02

            piping_results[conn.id] = PipingResult(
                component_id=conn.id,
                upstream_component_id=conn.from_component_id,
                downstream_component_id=conn.to_component_id,
                flow=flow_gpm if flow_m3s >= 0 else -flow_gpm,
                velocity=velocity_fps,
                head_loss=head_loss_ft,
                friction_head_loss=head_loss_ft * 0.8,  # Approximate
                minor_head_loss=head_loss_ft * 0.2,
                reynolds_number=max(reynolds, 1.0),
                friction_factor=max(friction_f, 0.001),
                regime=regime,
            )

        except (KeyError, IndexError) as e:
            logger.warning(f"Could not get results for link {wntr_link}: {e}")

    # Convert pump results
    pump_results: dict[str, PumpResult] = {}

    for comp in project.components:
        if not isinstance(comp, PumpComponent):
            continue

        if comp.id not in ctx.pump_map:
            continue

        wntr_pump = ctx.pump_map[comp.id]

        try:
            # Get pump flow and energy
            flow_m3s = link_results["flowrate"][wntr_pump].iloc[0]
            flow_gpm = abs(flow_m3s) * M3S_TO_GPM

            # Calculate operating head from pump curve
            pump_curve = project.get_pump_curve(comp.curve_id)
            if pump_curve:
                # Interpolate head from curve
                from .simple import build_pump_curve_interpolator

                interp = build_pump_curve_interpolator(pump_curve.points)
                operating_head = interp(flow_gpm)
            else:
                operating_head = 0.0

            # Get NPSH available (simplified calculation)
            npsh_a = 30.0  # Default assumption

            # Build system curve points
            system_curve: list[FlowHeadPoint] = []

            pump_results[comp.id] = PumpResult(
                component_id=comp.id,
                operating_flow=flow_gpm,
                operating_head=operating_head,
                npsh_available=npsh_a,
                system_curve=system_curve,
            )

        except (KeyError, IndexError) as e:
            logger.warning(f"Could not get results for pump {wntr_pump}: {e}")

    solve_time = perf_counter() - start_time

    return SolvedState(
        converged=True,
        iterations=1,
        timestamp=datetime.utcnow(),
        solve_time_seconds=solve_time,
        error=None,
        component_results=component_results,
        piping_results=piping_results,
        pump_results=pump_results,
        warnings=warnings,
    )


def solve_with_epanet(
    project: Project,
    fluid_props: FluidProperties,
) -> SolvedState:
    """Solve a project using EPANET via WNTR.

    This is the main entry point for EPANET-based solving. It handles
    the full workflow: build network, run simulation, convert results.

    Args:
        project: The project to solve
        fluid_props: Fluid properties

    Returns:
        SolvedState with results
    """
    start_time = perf_counter()

    # Build WNTR network
    ctx, build_warnings = build_wntr_network(project, fluid_props)

    # Check for build errors
    build_errors = [w for w in build_warnings if w.severity == WarningSeverity.ERROR]
    if build_errors:
        return SolvedState(
            converged=False,
            iterations=0,
            timestamp=datetime.utcnow(),
            solve_time_seconds=perf_counter() - start_time,
            error="Failed to build EPANET network: " + build_errors[0].message,
            warnings=build_warnings,
        )

    # Run simulation
    results, error = run_epanet_simulation(ctx)

    if error:
        return SolvedState(
            converged=False,
            iterations=0,
            timestamp=datetime.utcnow(),
            solve_time_seconds=perf_counter() - start_time,
            error=error,
            warnings=build_warnings,
        )

    # Convert results
    return convert_wntr_results(ctx, results, project, fluid_props, start_time)


__all__ = [
    "WNTRBuildContext",
    "build_wntr_network",
    "convert_wntr_results",
    "run_epanet_simulation",
    "solve_with_epanet",
]
