/**
 * Component models for hydraulic network elements.
 * Mirrors: apps/api/src/opensolve_pipe/models/components.py
 */

import type { PipingSegment } from './piping';

// ============================================================================
// Port Types
// ============================================================================

/** Direction of flow through a port. */
export type PortDirection = 'inlet' | 'outlet' | 'bidirectional';

/**
 * A connection port on a component.
 *
 * Ports define where pipes can connect to components. Each port has:
 * - A unique ID within the component (P1, P2, P3, etc.)
 * - A human-readable name describing the port's purpose
 * - A nominal size for pipe size matching
 * - A direction indicating flow constraints
 * - An optional elevation override for port-specific height
 *
 * If elevation is not specified (undefined), the port inherits the parent
 * component's elevation. This is useful for most equipment. For tall
 * equipment like tanks, reservoirs, or vertical pumps, port-specific
 * elevations can be set to model connection points at different heights.
 */
export interface Port {
	/** Unique port identifier within the component (P1, P2, P3, ...). */
	id: string;
	/** Human-readable name describing the port (e.g., 'Suction', 'Discharge'). */
	name: string;
	/** Nominal port size in project units (typically inches). */
	nominal_size: number;
	/** Flow direction constraint for this port. */
	direction: PortDirection;
	/** Optional port-specific elevation. If undefined, inherits from parent component. */
	elevation?: number;
}

/** Port-based connection between two components. */
export interface PipeConnection {
	/** Unique connection identifier. */
	id: string;
	/** Source component ID. */
	from_component_id: string;
	/** Source port ID on the from_component. */
	from_port_id: string;
	/** Target component ID. */
	to_component_id: string;
	/** Target port ID on the to_component. */
	to_port_id: string;
	/** Piping segment for this connection. */
	piping?: PipingSegment;
}

// ============================================================================
// Component Types
// ============================================================================

/** Types of network components. */
export type ComponentType =
	| 'reservoir'
	| 'tank'
	| 'junction'
	| 'pump'
	| 'valve'
	| 'heat_exchanger'
	| 'strainer'
	| 'orifice'
	| 'sprinkler'
	| 'ideal_reference_node'
	| 'non_ideal_reference_node'
	| 'plug'
	| 'tee_branch'
	| 'wye_branch'
	| 'cross_branch';

/** Display names for component types. */
export const COMPONENT_TYPE_LABELS: Record<ComponentType, string> = {
	reservoir: 'Reservoir',
	tank: 'Tank',
	junction: 'Junction',
	pump: 'Pump',
	valve: 'Valve',
	heat_exchanger: 'Heat Exchanger',
	strainer: 'Strainer',
	orifice: 'Orifice',
	sprinkler: 'Sprinkler',
	ideal_reference_node: 'Reference Node',
	non_ideal_reference_node: 'Reference Node',
	plug: 'Plug/Cap',
	tee_branch: 'Tee Branch',
	wye_branch: 'Wye Branch',
	cross_branch: 'Cross Branch'
};

/**
 * Component categories for UI grouping.
 * All equipment is grouped together - "links" (piping/fittings) connect components.
 * See ADR-006 in docs/DECISIONS.md for rationale.
 *
 * Note: 'ideal_reference_node' is used as the menu entry for Reference Node.
 * Users can switch to non-ideal within the component form.
 */
export const COMPONENT_CATEGORIES = {
	Sources: ['reservoir', 'tank', 'ideal_reference_node'] as ComponentType[],
	Equipment: ['pump', 'valve', 'heat_exchanger', 'strainer', 'orifice', 'sprinkler'] as ComponentType[],
	Connections: ['junction', 'tee_branch', 'wye_branch', 'cross_branch', 'plug'] as ComponentType[]
};

/** Types of control valves. */
export type ValveType =
	| 'gate'
	| 'ball'
	| 'butterfly'
	| 'globe'
	| 'check'
	| 'stop_check'
	| 'prv'
	| 'psv'
	| 'fcv'
	| 'tcv'
	| 'relief';

/** Display names for valve types. */
export const VALVE_TYPE_LABELS: Record<ValveType, string> = {
	gate: 'Gate Valve',
	ball: 'Ball Valve',
	butterfly: 'Butterfly Valve',
	globe: 'Globe Valve',
	check: 'Check Valve',
	stop_check: 'Stop Check Valve',
	prv: 'Pressure Reducing Valve (PRV)',
	psv: 'Pressure Sustaining Valve (PSV)',
	fcv: 'Flow Control Valve (FCV)',
	tcv: 'Throttle Control Valve (TCV)',
	relief: 'Relief Valve'
};

/** Valve types that require a setpoint. */
export const CONTROL_VALVE_TYPES: ValveType[] = ['prv', 'psv', 'fcv', 'tcv'];

/** Connection to a downstream component. */
export interface Connection {
	/** ID of the downstream component. */
	target_component_id: string;
	/** Piping segment to downstream component. */
	piping?: PipingSegment;
}

/** Base properties common to all components. */
interface BaseComponentProps {
	/** Unique component identifier. */
	id: string;
	/** Display name. */
	name: string;
	/** Component elevation (can be negative). */
	elevation: number;
	/** Connection ports for this component. */
	ports: Port[];
	/** Piping from upstream component (deprecated, use connections). */
	upstream_piping?: PipingSegment;
	/** Connections to downstream components (deprecated, use Project.connections). */
	downstream_connections: Connection[];
}

/** Fixed-head water source (infinite capacity). */
export interface Reservoir extends BaseComponentProps {
	type: 'reservoir';
	/** Water level above reservoir bottom. */
	water_level: number;
	/** Gauge pressure at water surface. Default: 0 (atmospheric). Units: project pressure units. */
	surface_pressure: number;
}

/** Variable-level storage tank. */
export interface Tank extends BaseComponentProps {
	type: 'tank';
	/** Tank diameter. */
	diameter: number;
	/** Minimum water level. Default: 0 */
	min_level: number;
	/** Maximum water level. */
	max_level: number;
	/** Initial water level. */
	initial_level: number;
	/** Gauge pressure at water surface. Default: 0 (atmospheric). Units: project pressure units. */
	surface_pressure: number;
}

/** Connection point, optionally with demand. */
export interface Junction extends BaseComponentProps {
	type: 'junction';
	/** Flow demand withdrawn at this junction. Default: 0 */
	demand: number;
}

/** Pump component that references a pump curve from the project library. */
export interface PumpComponent extends BaseComponentProps {
	type: 'pump';
	/** Reference to pump curve in project pump_library. */
	curve_id: string;
	/** Fraction of rated speed (1.0 = 100%). Default: 1.0 */
	speed: number;
	/** Pump status. Default: 'on' */
	status: 'on' | 'off';
}

/** Valve component for flow/pressure control. */
export interface ValveComponent extends BaseComponentProps {
	type: 'valve';
	/** Type of valve. */
	valve_type: ValveType;
	/** Setpoint for control valves (pressure or flow depending on type). */
	setpoint?: number;
	/** Valve position for throttling (0=closed, 1=open). */
	position?: number;
	/** Valve Cv coefficient (optional, for detailed model). */
	cv?: number;
}

/** Heat exchanger with known pressure drop. */
export interface HeatExchanger extends BaseComponentProps {
	type: 'heat_exchanger';
	/** Pressure drop at design flow (in project units). */
	pressure_drop: number;
	/** Design flow rate (in project units). */
	design_flow: number;
}

/** Strainer with known pressure drop or K-factor. */
export interface Strainer extends BaseComponentProps {
	type: 'strainer';
	/** K-factor for head loss calculation. */
	k_factor?: number;
	/** Fixed pressure drop (alternative to K-factor). */
	pressure_drop?: number;
	/** Design flow for fixed pressure drop. */
	design_flow?: number;
}

/** Orifice plate for flow measurement or restriction. */
export interface Orifice extends BaseComponentProps {
	type: 'orifice';
	/** Orifice diameter. */
	orifice_diameter: number;
	/** Discharge coefficient (Cd). Default: 0.62 */
	discharge_coefficient: number;
}

/** Sprinkler head with known K-factor. */
export interface Sprinkler extends BaseComponentProps {
	type: 'sprinkler';
	/** Sprinkler K-factor (flow = K * sqrt(pressure)). */
	k_factor: number;
	/** Design operating pressure. */
	design_pressure?: number;
}

// ============================================================================
// Reference Node Types
// ============================================================================

/** A point on a pressure-flow curve for non-ideal reference nodes. */
export interface FlowPressurePoint {
	/** Flow rate in project units. */
	flow: number;
	/** Pressure at this flow in project units. */
	pressure: number;
}

/** Ideal reference node with constant pressure. */
export interface IdealReferenceNode extends BaseComponentProps {
	type: 'ideal_reference_node';
	/** Fixed pressure in project units. */
	pressure: number;
}

/** Non-ideal reference node with pressure that varies with flow. */
export interface NonIdealReferenceNode extends BaseComponentProps {
	type: 'non_ideal_reference_node';
	/** Pressure-flow curve defining boundary behavior. */
	pressure_flow_curve: FlowPressurePoint[];
	/** Maximum flow capacity (optional). */
	max_flow?: number;
}

// ============================================================================
// Plug Type
// ============================================================================

/** Plug/Cap component for dead-end boundary conditions. */
export interface Plug extends BaseComponentProps {
	type: 'plug';
}

// ============================================================================
// Branch Types
// ============================================================================

/** Tee branch for 90° flow splitting/combining. */
export interface TeeBranch extends BaseComponentProps {
	type: 'tee_branch';
	/** Branch angle in degrees (45-90, standard tee is 90°). */
	branch_angle: number;
}

/** Wye branch for angled flow splitting/combining. */
export interface WyeBranch extends BaseComponentProps {
	type: 'wye_branch';
	/** Branch angle in degrees (22.5-60, common values: 45°, 60°). */
	branch_angle: number;
}

/** Cross fitting for four-way flow distribution. */
export interface CrossBranch extends BaseComponentProps {
	type: 'cross_branch';
}

/** Discriminated union for all component types. */
export type Component =
	| Reservoir
	| Tank
	| Junction
	| PumpComponent
	| ValveComponent
	| HeatExchanger
	| Strainer
	| Orifice
	| Sprinkler
	| IdealReferenceNode
	| NonIdealReferenceNode
	| Plug
	| TeeBranch
	| WyeBranch
	| CrossBranch;

// Type guards for component discrimination

/** Type guard for Reservoir. */
export function isReservoir(component: Component): component is Reservoir {
	return component.type === 'reservoir';
}

/** Type guard for Tank. */
export function isTank(component: Component): component is Tank {
	return component.type === 'tank';
}

/** Type guard for Junction. */
export function isJunction(component: Component): component is Junction {
	return component.type === 'junction';
}

/** Type guard for PumpComponent. */
export function isPump(component: Component): component is PumpComponent {
	return component.type === 'pump';
}

/** Type guard for ValveComponent. */
export function isValve(component: Component): component is ValveComponent {
	return component.type === 'valve';
}

/** Type guard for HeatExchanger. */
export function isHeatExchanger(component: Component): component is HeatExchanger {
	return component.type === 'heat_exchanger';
}

/** Type guard for Strainer. */
export function isStrainer(component: Component): component is Strainer {
	return component.type === 'strainer';
}

/** Type guard for Orifice. */
export function isOrifice(component: Component): component is Orifice {
	return component.type === 'orifice';
}

/** Type guard for Sprinkler. */
export function isSprinkler(component: Component): component is Sprinkler {
	return component.type === 'sprinkler';
}

/** Type guard for IdealReferenceNode. */
export function isIdealReferenceNode(component: Component): component is IdealReferenceNode {
	return component.type === 'ideal_reference_node';
}

/** Type guard for NonIdealReferenceNode. */
export function isNonIdealReferenceNode(component: Component): component is NonIdealReferenceNode {
	return component.type === 'non_ideal_reference_node';
}

/** Type guard for Plug. */
export function isPlug(component: Component): component is Plug {
	return component.type === 'plug';
}

/** Type guard for TeeBranch. */
export function isTeeBranch(component: Component): component is TeeBranch {
	return component.type === 'tee_branch';
}

/** Type guard for WyeBranch. */
export function isWyeBranch(component: Component): component is WyeBranch {
	return component.type === 'wye_branch';
}

/** Type guard for CrossBranch. */
export function isCrossBranch(component: Component): component is CrossBranch {
	return component.type === 'cross_branch';
}

/**
 * @deprecated Use COMPONENT_CATEGORIES.Equipment instead.
 * Legacy function - all components are now considered equipment.
 * The node/link distinction is an internal solver concept, not user-facing.
 * See ADR-006.
 */
export function isNodeComponent(component: Component): boolean {
	// Legacy: reservoir, tank, junction, sprinkler, orifice were "nodes"
	return ['reservoir', 'tank', 'junction', 'sprinkler', 'orifice'].includes(component.type);
}

/**
 * @deprecated Use COMPONENT_CATEGORIES.Equipment instead.
 * Legacy function - all components are now considered equipment.
 * The node/link distinction is an internal solver concept, not user-facing.
 * See ADR-006.
 */
export function isLinkComponent(component: Component): boolean {
	// Legacy: pump, valve, heat_exchanger, strainer were "links"
	return ['pump', 'valve', 'heat_exchanger', 'strainer'].includes(component.type);
}

/** Get total head for a reservoir (without pressure contribution). */
export function getReservoirTotalHead(reservoir: Reservoir): number {
	return reservoir.elevation + reservoir.water_level;
}

/**
 * Get total head for a reservoir including surface pressure contribution.
 * @param reservoir - The reservoir component
 * @param fluidDensity - Fluid density in kg/m³ (SI) or lb/ft³ (Imperial)
 * @param g - Gravitational acceleration (default: 9.80665 m/s²)
 * @returns Total head = elevation + water_level + pressure_head
 */
export function getReservoirTotalHeadWithPressure(
	reservoir: Reservoir,
	fluidDensity: number,
	g: number = 9.80665
): number {
	const pressureHead = reservoir.surface_pressure / (fluidDensity * g);
	return reservoir.elevation + reservoir.water_level + pressureHead;
}

/** Get total head for a tank (without pressure contribution). */
export function getTankTotalHead(tank: Tank): number {
	return tank.elevation + tank.initial_level;
}

/**
 * Get total head for a tank including surface pressure contribution.
 * @param tank - The tank component
 * @param fluidDensity - Fluid density in kg/m³ (SI) or lb/ft³ (Imperial)
 * @param g - Gravitational acceleration (default: 9.80665 m/s²)
 * @returns Total head = elevation + initial_level + pressure_head
 */
export function getTankTotalHeadWithPressure(
	tank: Tank,
	fluidDensity: number,
	g: number = 9.80665
): number {
	const pressureHead = tank.surface_pressure / (fluidDensity * g);
	return tank.elevation + tank.initial_level + pressureHead;
}

/**
 * Get the effective elevation for a port on a component.
 *
 * If the port has a specific elevation set, that value is returned.
 * Otherwise, the component's elevation is returned (inheritance).
 *
 * This is useful for modeling:
 * - Tanks/Reservoirs with ports at different heights (bottom drain, side fill, top overflow)
 * - Pumps with suction and discharge nozzles at different elevations
 * - Heat exchangers with shell/tube connections at different heights
 * - Vertical equipment where connection points span multiple elevations
 *
 * @param component - The component containing the port
 * @param portId - The ID of the port to get elevation for
 * @returns The effective elevation of the port
 * @throws Error if the port is not found on the component
 */
export function getPortElevation(component: Component, portId: string): number {
	const port = component.ports.find((p) => p.id === portId);
	if (!port) {
		throw new Error(`Port '${portId}' not found on component '${component.id}'`);
	}
	return port.elevation !== undefined ? port.elevation : component.elevation;
}

/** Generate a unique component ID. */
export function generateComponentId(): string {
	return `comp_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
}

// ============================================================================
// Port Factory Functions
// ============================================================================

/** Create default ports for a reservoir. */
export function createReservoirPorts(size: number = 4.0): Port[] {
	return [{ id: 'P1', name: 'Outlet', nominal_size: size, direction: 'bidirectional' }];
}

/** Create default ports for a tank. */
export function createTankPorts(size: number = 4.0): Port[] {
	return [{ id: 'P1', name: 'Port', nominal_size: size, direction: 'bidirectional' }];
}

/** Create default ports for a junction. */
export function createJunctionPorts(size: number = 4.0): Port[] {
	return [{ id: 'P1', name: 'Port', nominal_size: size, direction: 'bidirectional' }];
}

/** Create default ports for a pump. */
export function createPumpPorts(suctionSize: number = 4.0, dischargeSize: number = 4.0): Port[] {
	return [
		{ id: 'P1', name: 'Suction', nominal_size: suctionSize, direction: 'inlet' },
		{ id: 'P2', name: 'Discharge', nominal_size: dischargeSize, direction: 'outlet' }
	];
}

/** Create default ports for a valve. */
export function createValvePorts(size: number = 4.0): Port[] {
	return [
		{ id: 'P1', name: 'Inlet', nominal_size: size, direction: 'inlet' },
		{ id: 'P2', name: 'Outlet', nominal_size: size, direction: 'outlet' }
	];
}

/** Create default ports for a heat exchanger. */
export function createHeatExchangerPorts(size: number = 4.0): Port[] {
	return [
		{ id: 'P1', name: 'Inlet', nominal_size: size, direction: 'inlet' },
		{ id: 'P2', name: 'Outlet', nominal_size: size, direction: 'outlet' }
	];
}

/** Create default ports for a strainer. */
export function createStrainerPorts(size: number = 4.0): Port[] {
	return [
		{ id: 'P1', name: 'Inlet', nominal_size: size, direction: 'inlet' },
		{ id: 'P2', name: 'Outlet', nominal_size: size, direction: 'outlet' }
	];
}

/** Create default ports for an orifice. */
export function createOrificePorts(size: number = 4.0): Port[] {
	return [
		{ id: 'P1', name: 'Inlet', nominal_size: size, direction: 'inlet' },
		{ id: 'P2', name: 'Outlet', nominal_size: size, direction: 'outlet' }
	];
}

/** Create default ports for a sprinkler. */
export function createSprinklerPorts(size: number = 1.0): Port[] {
	return [{ id: 'P1', name: 'Inlet', nominal_size: size, direction: 'inlet' }];
}

/** Create default ports for a reference node. */
export function createReferenceNodePorts(size: number = 4.0): Port[] {
	return [{ id: 'P1', name: 'Port', nominal_size: size, direction: 'bidirectional' }];
}

/** Create default ports for a plug. */
export function createPlugPorts(size: number = 4.0): Port[] {
	return [{ id: 'P1', name: 'Port', nominal_size: size, direction: 'bidirectional' }];
}

/** Create default ports for a tee branch. */
export function createTeePorts(runSize: number = 4.0, branchSize?: number): Port[] {
	return [
		{ id: 'P1', name: 'Run Inlet', nominal_size: runSize, direction: 'bidirectional' },
		{ id: 'P2', name: 'Run Outlet', nominal_size: runSize, direction: 'bidirectional' },
		{ id: 'P3', name: 'Branch', nominal_size: branchSize ?? runSize, direction: 'bidirectional' }
	];
}

/** Create default ports for a wye branch. */
export function createWyePorts(runSize: number = 4.0, branchSize?: number): Port[] {
	return [
		{ id: 'P1', name: 'Run Inlet', nominal_size: runSize, direction: 'bidirectional' },
		{ id: 'P2', name: 'Run Outlet', nominal_size: runSize, direction: 'bidirectional' },
		{ id: 'P3', name: 'Branch', nominal_size: branchSize ?? runSize, direction: 'bidirectional' }
	];
}

/** Create default ports for a cross branch. */
export function createCrossPorts(mainSize: number = 4.0, branchSize?: number): Port[] {
	return [
		{ id: 'P1', name: 'Run Inlet', nominal_size: mainSize, direction: 'bidirectional' },
		{ id: 'P2', name: 'Run Outlet', nominal_size: mainSize, direction: 'bidirectional' },
		{ id: 'P3', name: 'Branch 1', nominal_size: branchSize ?? mainSize, direction: 'bidirectional' },
		{ id: 'P4', name: 'Branch 2', nominal_size: branchSize ?? mainSize, direction: 'bidirectional' }
	];
}

/** Get default ports for a component type. */
export function getDefaultPorts(type: ComponentType): Port[] {
	switch (type) {
		case 'reservoir':
			return createReservoirPorts();
		case 'tank':
			return createTankPorts();
		case 'junction':
			return createJunctionPorts();
		case 'pump':
			return createPumpPorts();
		case 'valve':
			return createValvePorts();
		case 'heat_exchanger':
			return createHeatExchangerPorts();
		case 'strainer':
			return createStrainerPorts();
		case 'orifice':
			return createOrificePorts();
		case 'sprinkler':
			return createSprinklerPorts();
		case 'ideal_reference_node':
		case 'non_ideal_reference_node':
			return createReferenceNodePorts();
		case 'plug':
			return createPlugPorts();
		case 'tee_branch':
			return createTeePorts();
		case 'wye_branch':
			return createWyePorts();
		case 'cross_branch':
			return createCrossPorts();
	}
}

/** Create a default component of the specified type. */
export function createDefaultComponent(type: ComponentType, id?: string): Component {
	const baseProps: BaseComponentProps = {
		id: id ?? generateComponentId(),
		name: `New ${COMPONENT_TYPE_LABELS[type]}`,
		elevation: 0,
		ports: getDefaultPorts(type),
		downstream_connections: []
	};

	switch (type) {
		case 'reservoir':
			return { ...baseProps, type: 'reservoir', water_level: 0, surface_pressure: 0 };
		case 'tank':
			return {
				...baseProps,
				type: 'tank',
				diameter: 10,
				min_level: 0,
				max_level: 20,
				initial_level: 10,
				surface_pressure: 0
			};
		case 'junction':
			return { ...baseProps, type: 'junction', demand: 0 };
		case 'pump':
			return { ...baseProps, type: 'pump', curve_id: '', speed: 1.0, status: 'on' };
		case 'valve':
			return { ...baseProps, type: 'valve', valve_type: 'gate' };
		case 'heat_exchanger':
			return { ...baseProps, type: 'heat_exchanger', pressure_drop: 5, design_flow: 100 };
		case 'strainer':
			return { ...baseProps, type: 'strainer', k_factor: 2.5 };
		case 'orifice':
			return {
				...baseProps,
				type: 'orifice',
				orifice_diameter: 2,
				discharge_coefficient: 0.62
			};
		case 'sprinkler':
			return { ...baseProps, type: 'sprinkler', k_factor: 5.6 };
		case 'ideal_reference_node':
			return { ...baseProps, type: 'ideal_reference_node', pressure: 50 };
		case 'non_ideal_reference_node':
			return {
				...baseProps,
				type: 'non_ideal_reference_node',
				pressure_flow_curve: [
					{ flow: 0, pressure: 60 },
					{ flow: 100, pressure: 50 }
				]
			};
		case 'plug':
			return { ...baseProps, type: 'plug' };
		case 'tee_branch':
			return { ...baseProps, type: 'tee_branch', branch_angle: 90 };
		case 'wye_branch':
			return { ...baseProps, type: 'wye_branch', branch_angle: 45 };
		case 'cross_branch':
			return { ...baseProps, type: 'cross_branch' };
	}
}
