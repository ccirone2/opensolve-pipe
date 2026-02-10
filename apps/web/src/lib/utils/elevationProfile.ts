/**
 * Elevation profile data transformation.
 *
 * Converts the project component chain + solved state into a flat array
 * of elements suitable for rendering the Elevation Profile SVG chart.
 */

import type {
	Component,
	Reservoir,
	Tank,
	PipeConnection
} from '$lib/models/components';
import {
	isReservoir,
	isTank,
	isPump,
	isValve
} from '$lib/models/components';
import type { SolvedState, ComponentResult, PipingResult } from '$lib/models/results';

// ============================================================================
// Types
// ============================================================================

/** An element in the elevation profile (component or connection). */
export interface ElevationElement {
	/** Element type: component or connection (pipe). */
	type: 'comp' | 'conn';
	/** Display name. */
	name: string;
	/** Component ID (for cross-referencing with results). */
	id: string;
	/** Elevation at port 1 (upstream). */
	p1_el: number;
	/** Elevation at port 2 (downstream), null if single-port. */
	p2_el: number | null;
	/** Minimum elevation (tank min water level or pipe low point). */
	min_el?: number;
	/** Maximum elevation (tank max water level, reservoir surface, or pipe high point). */
	max_el?: number;
	/** Pipe length (connections only, determines x-axis scaling). */
	length?: number;
	/** Head change across this element: negative = loss, positive = gain (pump). */
	head_change?: number;
}

// ============================================================================
// Helpers
// ============================================================================

/**
 * Get the effective elevation for a component port.
 * Uses port-specific elevation if set, otherwise falls back to component elevation.
 */
function getPortElevation(component: Component, portId: string): number {
	const port = component.ports.find((p) => p.id === portId);
	return port?.elevation ?? component.elevation;
}

/**
 * Compute the head change for a component from solved results.
 * For multi-port components (pumps, valves), uses the HGL difference
 * between discharge and suction ports. For single-port components,
 * uses exit/entry losses if available.
 */
function getComponentHeadChange(
	component: Component,
	results: SolvedState | null | undefined
): number | undefined {
	if (!results?.component_results) return undefined;

	if (isPump(component) || isValve(component)) {
		// Multi-port: look for suction/discharge or P1/P2 results
		const portIds = component.ports.map((p) => p.id);
		const portResults: ComponentResult[] = [];
		for (const key of Object.keys(results.component_results)) {
			const r = results.component_results[key];
			if (r.component_id === component.id) {
				portResults.push(r);
			}
		}

		if (portResults.length >= 2) {
			// Sort by port order (suction=P1 first, discharge=P2 second)
			const sorted = portResults.sort((a, b) => {
				const aIdx = portIds.indexOf(a.port_id);
				const bIdx = portIds.indexOf(b.port_id);
				return aIdx - bIdx;
			});
			return sorted[sorted.length - 1].hgl - sorted[0].hgl;
		}
	}

	// Single-port or fallback: look for a single result and check for losses
	const result = Object.values(results.component_results).find(
		(r) => r.component_id === component.id
	);
	if (result) {
		// For reservoirs/tanks/junctions, head change is typically small (entry/exit losses)
		// Return 0 for nodes without explicit head change
		return 0;
	}

	return undefined;
}

/**
 * Get the head loss for a piping connection from solved results.
 * Returns negative value (head loss).
 */
function getPipingHeadChange(
	connectionId: string,
	results: SolvedState | null | undefined
): number | undefined {
	if (!results?.piping_results) return undefined;

	// Try direct key match
	const result = results.piping_results[connectionId];
	if (result) return -result.head_loss;

	// Try pipe_ prefix
	const prefixed = results.piping_results[`pipe_${connectionId}`];
	if (prefixed) return -prefixed.head_loss;

	return undefined;
}

// ============================================================================
// Main function
// ============================================================================

/**
 * Build the elevation profile data from the project state and solved results.
 *
 * Walks the component chain following connections from upstream to downstream,
 * producing an ordered array of ElevationElements suitable for rendering.
 *
 * @param components - Ordered list of project components.
 * @param connections - Port-based connections between components.
 * @param results - Solved state (optional, for head_change values).
 * @returns Array of ElevationElements from upstream to downstream.
 */
export function buildElevationData(
	components: Component[],
	connections: PipeConnection[],
	results?: SolvedState | null
): ElevationElement[] {
	if (components.length === 0) return [];

	const elements: ElevationElement[] = [];

	// Build adjacency map: component ID → outgoing connections
	const outgoing = new Map<string, PipeConnection[]>();
	for (const conn of connections) {
		const existing = outgoing.get(conn.from_component_id) ?? [];
		existing.push(conn);
		outgoing.set(conn.from_component_id, existing);
	}

	// Build incoming map for finding root nodes
	const incoming = new Set<string>();
	for (const conn of connections) {
		incoming.add(conn.to_component_id);
	}

	// Find root component (no incoming connections) — typically the first reservoir/tank
	let rootId = components.find((c) => !incoming.has(c.id))?.id;
	if (!rootId) rootId = components[0]?.id;
	if (!rootId) return [];

	// Walk the chain from root using BFS (handles linear and simple branching)
	const visited = new Set<string>();
	const queue: string[] = [rootId];

	while (queue.length > 0) {
		const compId = queue.shift()!;
		if (visited.has(compId)) continue;
		visited.add(compId);

		const comp = components.find((c) => c.id === compId);
		if (!comp) continue;

		// Add component element
		const compElement: ElevationElement = {
			type: 'comp',
			name: comp.name,
			id: comp.id,
			p1_el: comp.elevation,
			p2_el: comp.ports.length > 1
				? getPortElevation(comp, comp.ports[comp.ports.length - 1].id)
				: null,
			head_change: getComponentHeadChange(comp, results)
		};

		// Add tank/reservoir-specific elevation ranges
		if (isReservoir(comp)) {
			compElement.max_el = comp.elevation + comp.water_level;
		} else if (isTank(comp)) {
			compElement.min_el = comp.elevation + comp.min_level;
			compElement.max_el = comp.elevation + comp.max_level;
		}

		elements.push(compElement);

		// Add outgoing connections as 'conn' elements
		const conns = outgoing.get(compId) ?? [];
		for (const conn of conns) {
			if (visited.has(conn.to_component_id)) continue;

			const pipeLength = conn.piping?.pipe?.length ?? 0;
			const fromEl = getPortElevation(comp, conn.from_port_id);
			const toComp = components.find((c) => c.id === conn.to_component_id);
			const toEl = toComp ? getPortElevation(toComp, conn.to_port_id) : fromEl;

			const connElement: ElevationElement = {
				type: 'conn',
				name: conn.id,
				id: conn.id,
				p1_el: fromEl,
				p2_el: toEl,
				length: pipeLength > 0 ? pipeLength : undefined,
				head_change: getPipingHeadChange(conn.id, results)
			};

			elements.push(connElement);
			queue.push(conn.to_component_id);
		}

		// If no outgoing connections, check downstream_connections (legacy field)
		if (conns.length === 0 && comp.downstream_connections?.length > 0) {
			for (const dc of comp.downstream_connections) {
				if (visited.has(dc.target_component_id)) continue;

				const pipeLength = dc.piping?.pipe?.length ?? 0;
				const toComp = components.find((c) => c.id === dc.target_component_id);
				const toEl = toComp?.elevation ?? comp.elevation;

				const connElement: ElevationElement = {
					type: 'conn',
					name: `pipe_${comp.id}_${dc.target_component_id}`,
					id: `pipe_${comp.id}_${dc.target_component_id}`,
					p1_el: comp.elevation,
					p2_el: toEl,
					length: pipeLength > 0 ? pipeLength : undefined,
					head_change: getPipingHeadChange(
						`pipe_${comp.id}_${dc.target_component_id}`,
						results
					)
				};

				elements.push(connElement);
				queue.push(dc.target_component_id);
			}
		}
	}

	return elements;
}
