/**
 * An assigned-flow node's flow (SDD §4.11, TSD §4.8) as the Build panel enters it and the results
 * show it: a direction (a demand, leaving the network at the port, or a supply, entering it) and
 * a magnitude in the display flow unit. The project stores one signed SI value, `flow` (m³/s,
 * positive leaves the network). A flow of 0 has no direction: the node passes no flow and behaves
 * exactly as a plug.
 *
 * The magnitude is stored as typed (converted to SI once, by the unit field) and the direction
 * only changes its sign, so a value round-trips exactly. Bounds come from the API schema
 * (`AssignedFlow.flow`), never from here.
 */
import type { UnitPreferences } from '../api/types';
import { schemaBounds, type Bounds } from './schema-bounds';
import { formatValue } from './units';

/** Demand: the flow leaves the network at the port (flow > 0); supply: it enters (flow < 0). */
export type FlowDirection = 'demand' | 'supply';

export const DIRECTION_LABELS: Readonly<Record<FlowDirection, string>> = {
	demand: 'Demand (leaves the network)',
	supply: 'Supply (enters the network)'
};

/** Short names, in results ("Demand", "Supply"). */
export const DIRECTION_NAMES: Readonly<Record<FlowDirection, string>> = {
	demand: 'Demand',
	supply: 'Supply'
};

/** The direction of a stored flow; null for 0, which has none. */
export function flowDirection(flow: number): FlowDirection | null {
	return flow > 0 ? 'demand' : flow < 0 ? 'supply' : null;
}

/** The stored flow for a magnitude (SI, ≥ 0) in a direction: a supply is negative; 0 is 0. */
export function signedFlow(magnitude: number, direction: FlowDirection): number {
	if (magnitude === 0) return 0;
	return direction === 'supply' ? -magnitude : magnitude;
}

/**
 * The bounds of the magnitude in a direction (SI), from the schema's bounds on the signed flow:
 * a demand up to its maximum, a supply up to minus its minimum.
 */
export function magnitudeBounds(direction: FlowDirection): Bounds {
	const signed = schemaBounds('AssignedFlow', 'flow');
	const bounds: Bounds = { minimum: 0 };
	if (direction === 'demand') {
		if (signed.maximum !== undefined) bounds.maximum = signed.maximum;
		if (signed.exclusiveMaximum !== undefined) bounds.exclusiveMaximum = signed.exclusiveMaximum;
	} else {
		if (signed.minimum !== undefined) bounds.maximum = -signed.minimum;
		if (signed.exclusiveMinimum !== undefined) bounds.exclusiveMaximum = -signed.exclusiveMinimum;
	}
	return bounds;
}

/** "Demand 5 L/s", "Supply 5 L/s", or "0 L/s (no flow, as a plug)": a flow as entered. */
export function assignedFlowText(flow: number, units: UnitPreferences): string {
	const direction = flowDirection(flow);
	const value = formatValue(Math.abs(flow), 'flow', units);
	return direction ? `${DIRECTION_NAMES[direction]} ${value}` : `${value} (no flow, as a plug)`;
}
