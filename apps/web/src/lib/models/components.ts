/**
 * Component models for hydraulic network elements.
 * Mirrors: apps/api/src/opensolve_pipe/models/components.py
 */

import type { PipingSegment } from './piping';

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
	| 'sprinkler';

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
	sprinkler: 'Sprinkler'
};

/** Component categories for UI grouping. */
export const COMPONENT_CATEGORIES = {
	Nodes: ['reservoir', 'tank', 'junction', 'sprinkler', 'orifice'] as ComponentType[],
	Links: ['pump', 'valve', 'heat_exchanger', 'strainer'] as ComponentType[]
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
	/** Piping from upstream component. */
	upstream_piping?: PipingSegment;
	/** Connections to downstream components. */
	downstream_connections: Connection[];
}

/** Fixed-head water source (infinite capacity). */
export interface Reservoir extends BaseComponentProps {
	type: 'reservoir';
	/** Water level above reservoir bottom. */
	water_level: number;
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
	| Sprinkler;

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

/** Check if a component is a node type (has pressure state). */
export function isNodeComponent(component: Component): boolean {
	return COMPONENT_CATEGORIES.Nodes.includes(component.type);
}

/** Check if a component is a link type (connects nodes). */
export function isLinkComponent(component: Component): boolean {
	return COMPONENT_CATEGORIES.Links.includes(component.type);
}

/** Get total head for a reservoir. */
export function getReservoirTotalHead(reservoir: Reservoir): number {
	return reservoir.elevation + reservoir.water_level;
}

/** Generate a unique component ID. */
export function generateComponentId(): string {
	return `comp_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
}

/** Create a default component of the specified type. */
export function createDefaultComponent(type: ComponentType, id?: string): Component {
	const baseProps: BaseComponentProps = {
		id: id ?? generateComponentId(),
		name: `New ${COMPONENT_TYPE_LABELS[type]}`,
		elevation: 0,
		downstream_connections: []
	};

	switch (type) {
		case 'reservoir':
			return { ...baseProps, type: 'reservoir', water_level: 0 };
		case 'tank':
			return {
				...baseProps,
				type: 'tank',
				diameter: 10,
				min_level: 0,
				max_level: 20,
				initial_level: 10
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
	}
}
