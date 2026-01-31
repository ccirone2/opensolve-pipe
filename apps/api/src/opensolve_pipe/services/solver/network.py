"""Network solver for complete project analysis.

This module implements the full project solver that handles:
- Simple single-path networks (delegated to simple solver)
- Branching networks (tees, wyes, crosses)
- Multiple boundary conditions (reservoirs, tanks, reference nodes, plugs)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from time import perf_counter
from typing import TYPE_CHECKING, Any

from ...models.components import ComponentType
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
from ...protocols import HeadSource
from ..fluids import get_fluid_properties_with_units
from .friction import calculate_pipe_head_loss_fps
from .k_factors import resolve_fittings_total_k
from .simple import (
    SimpleSolverOptions,
    build_pump_curve_interpolator,
    build_system_curve_function,
    calculate_npsh_available,
    find_operating_point,
    generate_system_curve,
)

if TYPE_CHECKING:
    from ...models.components import Component
    from ...models.connections import PipeConnection
    from ...models.fluids import FluidProperties
    from ...models.project import Project


class NetworkType(str, Enum):
    """Classification of network topology."""

    SIMPLE = "simple"  # Single path from source to sink
    BRANCHING = "branching"  # Tree structure with branches
    LOOPED = "looped"  # Contains loops/cycles


@dataclass
class NetworkGraph:
    """Graph representation of the hydraulic network."""

    # Component lookup by ID
    components: dict[str, Component] = field(default_factory=dict)

    # Connection lookup by ID
    connections: dict[str, PipeConnection] = field(default_factory=dict)

    # Adjacency lists
    outgoing: dict[str, list[str]] = field(
        default_factory=dict
    )  # component_id -> [connection_ids]
    incoming: dict[str, list[str]] = field(
        default_factory=dict
    )  # component_id -> [connection_ids]

    # Network classification
    network_type: NetworkType = NetworkType.SIMPLE

    # Source and sink components
    sources: list[str] = field(
        default_factory=list
    )  # Reservoirs, tanks, reference nodes
    sinks: list[str] = field(default_factory=list)  # Sprinklers, plugs, demands
    pumps: list[str] = field(default_factory=list)  # Pump components


@dataclass
class SolverState:
    """Mutable state during network solving."""

    # Pressures at each port (in ft of head), keyed by "{component_id}_{port_id}"
    port_pressures: dict[str, float] = field(default_factory=dict)

    # Legacy: Pressures at each component (in ft of head) - for backward compatibility
    pressures: dict[str, float] = field(default_factory=dict)

    # Flows through each connection (in GPM, positive = forward)
    flows: dict[str, float] = field(default_factory=dict)

    # Velocities in each connection (ft/s)
    velocities: dict[str, float] = field(default_factory=dict)

    # Head losses across each connection (ft)
    head_losses: dict[str, float] = field(default_factory=dict)

    # Reynolds numbers
    reynolds: dict[str, float] = field(default_factory=dict)

    # Friction factors
    friction_factors: dict[str, float] = field(default_factory=dict)

    # Warnings collected during solving
    warnings: list[Warning] = field(default_factory=list)

    # Pump-specific data (operating point, system curve, NPSH)
    _pump_data: dict[str, dict[str, Any]] = field(default_factory=dict)


def build_network_graph(project: Project) -> NetworkGraph:
    """Build a graph representation of the project network.

    Args:
        project: The project to analyze

    Returns:
        NetworkGraph with components, connections, and topology info
    """
    graph = NetworkGraph()

    # Index components
    for comp in project.components:
        graph.components[comp.id] = comp
        graph.outgoing[comp.id] = []
        graph.incoming[comp.id] = []

        # Classify by type
        # Note: Tanks are NOT sources - they are storage with variable level
        # Only reservoirs and reference nodes are true pressure/head sources
        if comp.type in (
            ComponentType.RESERVOIR,
            ComponentType.IDEAL_REFERENCE_NODE,
            ComponentType.NON_IDEAL_REFERENCE_NODE,
        ):
            graph.sources.append(comp.id)
        elif comp.type == ComponentType.PUMP:
            graph.pumps.append(comp.id)
        elif comp.type == ComponentType.PLUG or comp.type == ComponentType.SPRINKLER:  # type: ignore[comparison-overlap]
            graph.sinks.append(comp.id)
        elif (
            comp.type == ComponentType.JUNCTION
            and hasattr(comp, "demand")
            and comp.demand > 0
        ):
            # Junction is a sink if it has demand
            graph.sinks.append(comp.id)

    # Index connections
    for conn in project.connections:
        graph.connections[conn.id] = conn
        graph.outgoing[conn.from_component_id].append(conn.id)
        graph.incoming[conn.to_component_id].append(conn.id)

    # Classify network type
    graph.network_type = classify_network(graph)

    return graph


def classify_network(graph: NetworkGraph) -> NetworkType:
    """Classify the network topology.

    Args:
        graph: The network graph to classify

    Returns:
        NetworkType classification
    """
    # Check for branch components or multiple connections
    has_branches = False
    has_multiple_connections = False
    for comp_id, comp in graph.components.items():
        if comp.type in (
            ComponentType.TEE_BRANCH,
            ComponentType.WYE_BRANCH,
            ComponentType.CROSS_BRANCH,
        ):
            has_branches = True
        if len(graph.outgoing.get(comp_id, [])) > 1:
            has_multiple_connections = True
        if len(graph.incoming.get(comp_id, [])) > 1:
            has_multiple_connections = True

    # If we have branches or multiple connections, check for cycles
    if has_branches or has_multiple_connections:
        # Check for loops using DFS
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)

            for conn_id in graph.outgoing.get(node, []):
                conn = graph.connections[conn_id]
                neighbor = conn.to_component_id

                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        # Check from each source
        for source in graph.sources:
            if source not in visited and has_cycle(source):
                return NetworkType.LOOPED

        return NetworkType.BRANCHING

    return NetworkType.SIMPLE


def get_source_head(component: Component) -> float:
    """Get the total head at a source component.

    Uses the HeadSource protocol - any component with a total_head property
    can be used as a source.

    Args:
        component: Source component implementing HeadSource protocol
                   (reservoir, tank, or reference node)

    Returns:
        Total head in feet
    """
    if isinstance(component, HeadSource):
        return component.total_head
    # Fallback for components without total_head property
    return component.elevation


def solve_simple_path(
    project: Project,
    graph: NetworkGraph,
    fluid_props: FluidProperties,
    options: SimpleSolverOptions,
) -> tuple[SolverState, bool, str | None]:
    """Solve a simple single-path network.

    Args:
        project: The project to solve
        graph: Network graph
        fluid_props: Fluid properties
        options: Solver options

    Returns:
        Tuple of (SolverState, converged, error_message)
    """
    state = SolverState()

    # Find the source
    if not graph.sources:
        return (
            state,
            False,
            "No source component found (reservoir, tank, or reference node)",
        )

    source_id = graph.sources[0]
    source = graph.components[source_id]

    # Find the pump
    if not graph.pumps:
        return state, False, "No pump found in network"

    pump_id = graph.pumps[0]
    pump_comp = graph.components[pump_id]

    # Get pump curve - pump_comp must be PumpComponent since it's in graph.pumps
    from ...models.components import PumpComponent

    if not isinstance(pump_comp, PumpComponent):
        return state, False, f"Component '{pump_id}' is not a pump"

    pump_curve = project.get_pump_curve(pump_comp.curve_id)
    if pump_curve is None:
        return state, False, f"Pump curve '{pump_comp.curve_id}' not found"

    # Calculate total static head
    # Find the end of the path
    end_component = None
    current_id = source_id
    visited = {source_id}

    while graph.outgoing.get(current_id):
        conn_id = graph.outgoing[current_id][0]
        conn = graph.connections[conn_id]
        next_id = conn.to_component_id

        if next_id in visited:
            break
        visited.add(next_id)
        current_id = next_id
        end_component = graph.components[next_id]

    if end_component is None:
        return state, False, "Could not find end of flow path"

    # Static head = end elevation - source total head
    source_head = get_source_head(source)
    end_elevation = end_component.elevation
    static_head_ft = end_elevation - source_head

    # Calculate total pipe length, diameter, roughness, and K-factors
    total_length_ft = 0.0
    total_k_factor = 0.0
    pipe_diameter_in = 4.0  # Default
    pipe_roughness_in = 0.0018  # Default for steel

    # Track suction side parameters
    suction_head_ft = 0.0
    suction_losses_ft = 0.0

    for conn in project.connections:
        if conn.piping and conn.piping.pipe:
            pipe = conn.piping.pipe
            total_length_ft += pipe.length
            pipe_diameter_in = pipe.nominal_diameter

            # Use roughness override or default based on material
            if pipe.roughness_override is not None:
                pipe_roughness_in = pipe.roughness_override
            else:
                # Default roughness by material (in inches)
                roughness_map = {
                    "carbon_steel": 0.0018,
                    "stainless_steel": 0.00006,
                    "pvc": 0.00006,
                    "hdpe": 0.00006,
                    "copper": 0.00006,
                    "cast_iron": 0.01,
                    "ductile_iron": 0.01,
                    "concrete": 0.012,
                }
                pipe_roughness_in = roughness_map.get(
                    pipe.material.value
                    if hasattr(pipe.material, "value")
                    else str(pipe.material),
                    0.0018,
                )

            # Sum K-factors from fittings
            if conn.piping.fittings:
                total_k_factor += resolve_fittings_total_k(
                    conn.piping.fittings, pipe_diameter_in
                )

            # Check if this connection is on suction side of pump
            if conn.to_component_id == pump_id:
                # This is suction piping
                suction_head_ft = source_head - pump_comp.elevation

    # Convert kinematic viscosity to ft²/s
    nu_ft2s = fluid_props.kinematic_viscosity * 10.7639  # m²/s to ft²/s

    # Convert vapor pressure to psi
    vapor_pressure_psi = fluid_props.vapor_pressure * 0.000145038  # Pa to psi

    # Build pump curve interpolator
    pump_curve_points = pump_curve.points
    pump_interp = build_pump_curve_interpolator(pump_curve_points)

    # Build system curve function
    system_func = build_system_curve_function(
        static_head_ft=static_head_ft,
        pipe_length_ft=total_length_ft,
        pipe_diameter_in=pipe_diameter_in,
        pipe_roughness_in=pipe_roughness_in,
        kinematic_viscosity_ft2s=nu_ft2s,
        total_k_factor=total_k_factor,
    )

    # Check if pump can overcome static head
    shutoff_head = pump_interp(options.flow_min_gpm)
    if shutoff_head < static_head_ft:
        return (
            state,
            False,
            (
                f"Pump shutoff head ({shutoff_head:.1f} ft) is less than "
                f"static head ({static_head_ft:.1f} ft). Pump cannot overcome system."
            ),
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
        return state, False, "Could not find pump-system curve intersection"

    operating_flow, operating_head = result

    # Calculate detailed results
    _h_loss, velocity, reynolds, friction_f = calculate_pipe_head_loss_fps(
        length_ft=total_length_ft,
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
        fluid_specific_gravity=fluid_props.specific_gravity,
    )

    # Populate state with results
    # Set flows and hydraulic data for all connections
    for conn in project.connections:
        state.flows[conn.id] = operating_flow
        state.velocities[conn.id] = velocity
        state.reynolds[conn.id] = reynolds
        state.friction_factors[conn.id] = friction_f

        # Calculate head loss for this specific connection
        if conn.piping and conn.piping.pipe:
            pipe = conn.piping.pipe
            conn_k = 0.0
            if conn.piping.fittings:
                conn_k = resolve_fittings_total_k(
                    conn.piping.fittings, pipe.nominal_diameter
                )

            conn_h_loss, _, _, _ = calculate_pipe_head_loss_fps(
                length_ft=pipe.length,
                diameter_in=pipe.nominal_diameter,
                roughness_in=pipe_roughness_in,
                flow_gpm=operating_flow,
                kinematic_viscosity_ft2s=nu_ft2s,
                k_factor=conn_k,
            )
            state.head_losses[conn.id] = conn_h_loss
        else:
            state.head_losses[conn.id] = 0.0

    # Calculate pressures at each component port (propagate from source)
    current_pressure = source_head  # Start at source total head
    current_id = source_id
    visited = {source_id}

    # Store pressure for source component
    state.pressures[source_id] = current_pressure
    # Store port-level pressure for source (use first port or "default")
    source_comp = graph.components[source_id]
    source_ports = getattr(source_comp, "ports", [])
    if source_ports:
        for port in source_ports:
            port_key = f"{source_id}_{port.id}"
            state.port_pressures[port_key] = current_pressure
    else:
        state.port_pressures[f"{source_id}_default"] = current_pressure

    while graph.outgoing.get(current_id):
        conn_id = graph.outgoing[current_id][0]
        conn = graph.connections[conn_id]
        next_id = conn.to_component_id

        if next_id in visited:
            break
        visited.add(next_id)

        # Adjust pressure based on component type and head loss
        next_comp = graph.components[next_id]
        h_loss_conn = state.head_losses.get(conn_id, 0.0)
        next_ports = getattr(next_comp, "ports", [])

        if next_comp.type == ComponentType.PUMP:
            # Pump: suction port gets pressure before pump, discharge gets pressure after
            suction_pressure = current_pressure - h_loss_conn
            discharge_pressure = suction_pressure + operating_head

            # Find suction and discharge port IDs
            suction_port_id = "suction"
            discharge_port_id = "discharge"
            for port in next_ports:
                if port.direction == "inlet":
                    suction_port_id = port.id
                elif port.direction == "outlet":
                    discharge_port_id = port.id

            state.port_pressures[f"{next_id}_{suction_port_id}"] = suction_pressure
            state.port_pressures[f"{next_id}_{discharge_port_id}"] = discharge_pressure

            # Legacy: store discharge pressure as component pressure
            current_pressure = discharge_pressure
        elif next_comp.type == ComponentType.VALVE:
            # Valve: inlet gets pressure before drop, outlet gets pressure after
            inlet_pressure = current_pressure - h_loss_conn
            # For valves, we need to calculate the pressure drop across the valve
            # For now, use a simplified model where valve adds no additional loss
            # (the h_loss_conn includes piping loss, not valve-specific loss)
            outlet_pressure = inlet_pressure

            # Find inlet and outlet port IDs
            inlet_port_id = "inlet"
            outlet_port_id = "outlet"
            for port in next_ports:
                if port.direction == "inlet":
                    inlet_port_id = port.id
                elif port.direction == "outlet":
                    outlet_port_id = port.id

            state.port_pressures[f"{next_id}_{inlet_port_id}"] = inlet_pressure
            state.port_pressures[f"{next_id}_{outlet_port_id}"] = outlet_pressure

            current_pressure = outlet_pressure
        else:
            # All other components just have head loss and elevation change
            elevation_change = (
                next_comp.elevation - graph.components[current_id].elevation
            )
            current_pressure = current_pressure - h_loss_conn - elevation_change

            # Store port-level pressures for all ports on this component
            if next_ports:
                for port in next_ports:
                    port_key = f"{next_id}_{port.id}"
                    state.port_pressures[port_key] = current_pressure
            else:
                state.port_pressures[f"{next_id}_default"] = current_pressure

        state.pressures[next_id] = current_pressure
        current_id = next_id

    # Add velocity warning if needed
    if velocity > 10.0:
        state.warnings.append(
            Warning(
                category=WarningCategory.VELOCITY,
                severity=WarningSeverity.WARNING,
                message=f"Velocity ({velocity:.1f} ft/s) exceeds 10 ft/s maximum recommended",
                details={"velocity_fps": velocity},
            )
        )
    elif velocity < 2.0:
        state.warnings.append(
            Warning(
                category=WarningCategory.VELOCITY,
                severity=WarningSeverity.INFO,
                message=f"Velocity ({velocity:.1f} ft/s) is below 2 ft/s minimum recommended",
                details={"velocity_fps": velocity},
            )
        )

    # Add NPSH warning if margin is low
    if pump_curve.npshr_curve:
        # Find NPSHR at operating point by interpolation
        npshr_points = sorted(pump_curve.npshr_curve, key=lambda p: p.flow)
        # Simple linear interpolation
        for i in range(len(npshr_points) - 1):
            if npshr_points[i].flow <= operating_flow <= npshr_points[i + 1].flow:
                t = (operating_flow - npshr_points[i].flow) / (
                    npshr_points[i + 1].flow - npshr_points[i].flow
                )
                npshr = npshr_points[i].npsh_required + t * (
                    npshr_points[i + 1].npsh_required - npshr_points[i].npsh_required
                )
                npsh_margin = npsh_a - npshr
                if npsh_margin < 3.0:
                    state.warnings.append(
                        Warning(
                            category=WarningCategory.NPSH,
                            severity=WarningSeverity.WARNING
                            if npsh_margin < 0
                            else WarningSeverity.INFO,
                            component_id=pump_id,
                            message=f"NPSH margin ({npsh_margin:.1f} ft) is {'negative' if npsh_margin < 0 else 'low'}",
                            details={
                                "npsh_available": npsh_a,
                                "npsh_required": npshr,
                                "margin": npsh_margin,
                            },
                        )
                    )
                break

    # Store pump-specific data in state for later extraction
    state._pump_data = {
        pump_id: {
            "operating_flow": operating_flow,
            "operating_head": operating_head,
            "npsh_available": npsh_a,
            "system_curve": generate_system_curve(
                static_head_ft=static_head_ft,
                pipe_length_ft=total_length_ft,
                pipe_diameter_in=pipe_diameter_in,
                pipe_roughness_in=pipe_roughness_in,
                kinematic_viscosity_ft2s=nu_ft2s,
                total_k_factor=total_k_factor,
                flow_min_gpm=options.flow_min_gpm,
                flow_max_gpm=min(options.flow_max_gpm, operating_flow * 1.5),
                num_points=options.num_curve_points,
            ),
        }
    }

    return state, True, None


def solve_branching_network(
    project: Project,
    graph: NetworkGraph,
    fluid_props: FluidProperties,
    options: SimpleSolverOptions,
) -> tuple[SolverState, bool, str | None]:
    """Solve a branching network.

    For branching networks, we use an iterative approach:
    1. Start with initial flow estimates
    2. Apply flow continuity at each junction
    3. Calculate head losses
    4. Adjust flows until convergence

    Args:
        project: The project to solve
        graph: Network graph
        fluid_props: Fluid properties
        options: Solver options

    Returns:
        Tuple of (SolverState, converged, error_message)
    """
    state = SolverState()

    # For now, we only support tree-structured branching (no loops)
    # A full implementation would use WNTR/EPANET

    # Find all sources
    if not graph.sources:
        return state, False, "No source component found"

    # Find all pumps
    if not graph.pumps:
        # Network without pumps - gravity fed
        pass

    # Convert kinematic viscosity to ft²/s
    nu_ft2s = fluid_props.kinematic_viscosity * 10.7639

    # For tree-structured networks, we can solve by:
    # 1. Traverse from sources to sinks
    # 2. At each branch, split flow based on downstream resistance

    # Initialize flows with estimates
    initial_flow = 100.0  # GPM estimate
    for conn_id in graph.connections:
        state.flows[conn_id] = initial_flow

    # Simple iterative solver for tree networks
    max_iterations = options.max_iterations
    tolerance = options.tolerance

    converged = False

    for _iteration in range(max_iterations):
        max_error = 0.0

        # For each component, apply flow continuity
        for comp_id, comp in graph.components.items():
            if comp.type in (
                ComponentType.TEE_BRANCH,
                ComponentType.WYE_BRANCH,
                ComponentType.CROSS_BRANCH,
            ):
                # Branch component - sum of flows must equal zero
                # (flow in = flow out)
                incoming_conns = graph.incoming.get(comp_id, [])
                outgoing_conns = graph.outgoing.get(comp_id, [])

                total_in = sum(state.flows.get(c, 0) for c in incoming_conns)
                total_out = sum(state.flows.get(c, 0) for c in outgoing_conns)

                imbalance = total_in - total_out

                if abs(imbalance) > tolerance and outgoing_conns:
                    # Distribute imbalance to outgoing connections
                    adjustment = imbalance / len(outgoing_conns)
                    for conn_id in outgoing_conns:
                        state.flows[conn_id] += adjustment

                max_error = max(max_error, abs(imbalance))

        if max_error < tolerance:
            converged = True
            break

    if not converged:
        state.warnings.append(
            Warning(
                category=WarningCategory.CONVERGENCE,
                severity=WarningSeverity.WARNING,
                message=f"Solver did not converge after {max_iterations} iterations",
                details={"max_error": max_error},
            )
        )

    # Calculate velocities and head losses for each connection
    for conn_id, conn in graph.connections.items():
        flow = state.flows[conn_id]

        if conn.piping and conn.piping.pipe:
            pipe = conn.piping.pipe
            pipe_diameter_in = pipe.nominal_diameter

            # Get roughness
            if pipe.roughness_override is not None:
                pipe_roughness_in = pipe.roughness_override
            else:
                roughness_map = {
                    "carbon_steel": 0.0018,
                    "stainless_steel": 0.00006,
                    "pvc": 0.00006,
                    "hdpe": 0.00006,
                }
                pipe_roughness_in = roughness_map.get(
                    pipe.material.value
                    if hasattr(pipe.material, "value")
                    else str(pipe.material),
                    0.0018,
                )

            # K-factors from fittings
            k_factor = 0.0
            if conn.piping.fittings:
                k_factor = resolve_fittings_total_k(
                    conn.piping.fittings, pipe_diameter_in
                )

            h_loss, velocity, reynolds, friction_f = calculate_pipe_head_loss_fps(
                length_ft=pipe.length,
                diameter_in=pipe_diameter_in,
                roughness_in=pipe_roughness_in,
                flow_gpm=abs(flow),
                kinematic_viscosity_ft2s=nu_ft2s,
                k_factor=k_factor,
            )

            state.velocities[conn_id] = velocity
            state.head_losses[conn_id] = h_loss
            state.reynolds[conn_id] = reynolds
            state.friction_factors[conn_id] = friction_f
        else:
            state.velocities[conn_id] = 0.0
            state.head_losses[conn_id] = 0.0
            state.reynolds[conn_id] = 0.0
            state.friction_factors[conn_id] = 0.0

    # Calculate pressures at each component
    for source_id in graph.sources:
        source = graph.components[source_id]
        source_head = get_source_head(source)
        state.pressures[source_id] = source_head

        # BFS to propagate pressures
        queue = [source_id]
        visited = {source_id}

        while queue:
            current_id = queue.pop(0)
            current_pressure = state.pressures[current_id]

            for conn_id in graph.outgoing.get(current_id, []):
                conn = graph.connections[conn_id]
                next_id = conn.to_component_id

                if next_id in visited:
                    continue

                next_comp = graph.components[next_id]
                h_loss = state.head_losses.get(conn_id, 0.0)
                elevation_change = (
                    next_comp.elevation - graph.components[current_id].elevation
                )

                # Check if next component is a pump
                if next_comp.type == ComponentType.PUMP:
                    # Get pump curve and find operating point
                    pump_curve = project.get_pump_curve(next_comp.curve_id)
                    if pump_curve:
                        pump_interp = build_pump_curve_interpolator(pump_curve.points)
                        flow = abs(state.flows.get(conn_id, 0))
                        pump_head = pump_interp(flow) if flow > 0 else pump_interp(0.1)
                        state.pressures[next_id] = current_pressure - h_loss + pump_head
                    else:
                        state.pressures[next_id] = (
                            current_pressure - h_loss - elevation_change
                        )
                else:
                    state.pressures[next_id] = (
                        current_pressure - h_loss - elevation_change
                    )

                visited.add(next_id)
                queue.append(next_id)

    return state, converged, None


def solve_project(project: Project) -> SolvedState:
    """Solve a complete project and return the solved state.

    This is the main entry point for project solving. Uses the solver
    registry to select the appropriate solver strategy based on network
    topology.

    Args:
        project: The project to solve

    Returns:
        SolvedState with all results
    """
    # Import here to avoid circular imports
    from .registry import default_registry

    start_time = perf_counter()
    warnings: list[Warning] = []

    # Get fluid properties
    try:
        fluid_props = get_fluid_properties_with_units(project.fluid, "F")
    except Exception as e:
        return SolvedState(
            converged=False,
            iterations=0,
            timestamp=datetime.utcnow(),
            solve_time_seconds=perf_counter() - start_time,
            error=f"Failed to get fluid properties: {e}",
            warnings=[
                Warning(
                    category=WarningCategory.DATA,
                    severity=WarningSeverity.ERROR,
                    message=f"Fluid properties error: {e}",
                )
            ],
        )

    # Build network graph for validation
    graph = build_network_graph(project)

    # Check for valid network
    if not graph.components:
        return SolvedState(
            converged=False,
            iterations=0,
            timestamp=datetime.utcnow(),
            solve_time_seconds=perf_counter() - start_time,
            error="No components in network",
            warnings=[
                Warning(
                    category=WarningCategory.TOPOLOGY,
                    severity=WarningSeverity.ERROR,
                    message="Network has no components",
                )
            ],
        )

    if not graph.sources:
        return SolvedState(
            converged=False,
            iterations=0,
            timestamp=datetime.utcnow(),
            solve_time_seconds=perf_counter() - start_time,
            error="No source component found (reservoir, tank, or reference node)",
            warnings=[
                Warning(
                    category=WarningCategory.TOPOLOGY,
                    severity=WarningSeverity.ERROR,
                    message="Network has no source (reservoir, tank, or reference node)",
                )
            ],
        )

    # Configure solver options
    options = SimpleSolverOptions(
        max_iterations=project.settings.solver_options.max_iterations,
        tolerance=project.settings.solver_options.tolerance,
        flow_min_gpm=project.settings.solver_options.flow_range_min,
        flow_max_gpm=project.settings.solver_options.flow_range_max,
        num_curve_points=project.settings.solver_options.flow_points,
    )

    # Use registry to select appropriate solver
    solver = default_registry.get_solver(project)
    if solver is None:
        # No solver available for this network type (e.g., looped networks)
        return SolvedState(
            converged=False,
            iterations=0,
            timestamp=datetime.utcnow(),
            solve_time_seconds=perf_counter() - start_time,
            error="No solver available for this network topology. "
            "Looped networks require EPANET integration (not yet implemented).",
            warnings=[
                Warning(
                    category=WarningCategory.TOPOLOGY,
                    severity=WarningSeverity.ERROR,
                    message="No solver available for this network type",
                )
            ],
        )

    # Solve using the selected strategy
    state, converged, error = solver.solve(project, fluid_props, options)

    # Collect warnings
    warnings.extend(state.warnings)

    # Build result objects - now using port-level pressures
    component_results: dict[str, ComponentResult] = {}

    # First, emit results from port_pressures (port-level data)
    for port_key, pressure in state.port_pressures.items():
        # Parse the port key: "{component_id}_{port_id}"
        parts = port_key.rsplit("_", 1)
        if len(parts) == 2:
            comp_id, port_id = parts
        else:
            comp_id = port_key
            port_id = "default"

        # Convert head to pressure (psi) for results
        pressure_psi = pressure * 0.433  # ft of water to psi

        component_results[port_key] = ComponentResult(
            component_id=comp_id,
            port_id=port_id,
            pressure=pressure_psi,
            dynamic_pressure=0.0,  # Simplified - not calculating velocity head at each point
            total_pressure=pressure_psi,
            hgl=pressure,  # HGL is the pressure head
            egl=pressure,  # Simplified - EGL = HGL + velocity head
        )

    # Fallback: Add any components that don't have port-level data
    # (for backward compatibility with older solver paths)
    for comp_id in graph.components:
        if comp_id not in state.port_pressures and not any(
            k.startswith(f"{comp_id}_") for k in state.port_pressures
        ):
            pressure = state.pressures.get(comp_id, 0.0)
            pressure_psi = pressure * 0.433

            component_results[f"{comp_id}_default"] = ComponentResult(
                component_id=comp_id,
                port_id="default",
                pressure=pressure_psi,
                dynamic_pressure=0.0,
                total_pressure=pressure_psi,
                hgl=pressure,
                egl=pressure,
            )

    piping_results: dict[str, PipingResult] = {}
    for conn_id, conn in graph.connections.items():
        flow = state.flows.get(conn_id, 0.0)
        velocity = state.velocities.get(conn_id, 0.0)
        h_loss = state.head_losses.get(conn_id, 0.0)
        reynolds = state.reynolds.get(conn_id, 0.0)
        friction_f = state.friction_factors.get(conn_id, 0.0)

        # Determine flow regime
        if reynolds < 2300:
            regime = FlowRegime.LAMINAR
        elif reynolds < 4000:
            regime = FlowRegime.TRANSITIONAL
        else:
            regime = FlowRegime.TURBULENT

        piping_results[conn_id] = PipingResult(
            component_id=conn_id,
            upstream_component_id=conn.from_component_id,
            downstream_component_id=conn.to_component_id,
            flow=flow,
            velocity=velocity,
            head_loss=h_loss,
            friction_head_loss=h_loss * 0.8,  # Approximate split
            minor_head_loss=h_loss * 0.2,
            reynolds_number=max(reynolds, 1.0),  # Avoid zero
            friction_factor=max(friction_f, 0.001),  # Avoid zero
            regime=regime,
        )

    pump_results: dict[str, PumpResult] = {}
    for pump_id, pump_data in state._pump_data.items():
        from ...models.pump import FlowHeadPoint

        # Filter out negative head values (can occur with negative static head)
        system_curve_points = [
            FlowHeadPoint(flow=pt[0], head=max(0.0, pt[1]))
            for pt in pump_data.get("system_curve", [])
        ]

        pump_results[pump_id] = PumpResult(
            component_id=pump_id,
            operating_flow=pump_data["operating_flow"],
            operating_head=pump_data["operating_head"],
            npsh_available=pump_data["npsh_available"],
            system_curve=system_curve_points,
        )

    solve_time = perf_counter() - start_time

    return SolvedState(
        converged=converged,
        iterations=1 if converged else 0,
        timestamp=datetime.utcnow(),
        solve_time_seconds=solve_time,
        error=error,
        component_results=component_results,
        piping_results=piping_results,
        pump_results=pump_results,
        warnings=warnings,
    )


__all__ = [
    "NetworkGraph",
    "NetworkType",
    "SolverState",
    "build_network_graph",
    "classify_network",
    "solve_project",
]
