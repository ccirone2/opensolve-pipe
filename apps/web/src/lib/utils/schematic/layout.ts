/**
 * Graph layout algorithm for hydraulic network schematics.
 *
 * This module provides automatic positioning of components in the schematic view.
 * It follows a left-to-right flow layout optimized for hydraulic networks.
 */

import type { Component, PipeConnection } from '$lib/models';

// ============================================================================
// Types
// ============================================================================

/** Position of a component in the schematic. */
export interface ComponentPosition {
	/** Component ID. */
	id: string;
	/** X position (pixels). */
	x: number;
	/** Y position (pixels). */
	y: number;
	/** Calculated width for the component symbol. */
	width: number;
	/** Calculated height for the component symbol. */
	height: number;
}

/** A connection line between two components. */
export interface ConnectionLine {
	/** Connection ID. */
	id: string;
	/** Source component ID. */
	fromId: string;
	/** Target component ID. */
	toId: string;
	/** Source port ID. */
	fromPort: string;
	/** Target port ID. */
	toPort: string;
	/** Path points for the connection line. */
	points: Array<{ x: number; y: number }>;
}

/** Layout result containing positioned components and connection lines. */
export interface LayoutResult {
	/** Positioned components. */
	components: ComponentPosition[];
	/** Connection lines between components. */
	connections: ConnectionLine[];
	/** Bounding box of the entire layout. */
	bounds: {
		x: number;
		y: number;
		width: number;
		height: number;
	};
}

/** Options for the layout algorithm. */
export interface LayoutOptions {
	/** Horizontal spacing between components (default: 120). */
	horizontalSpacing?: number;
	/** Vertical spacing between parallel branches (default: 100). */
	verticalSpacing?: number;
	/** Default component width (default: 60). */
	componentWidth?: number;
	/** Default component height (default: 40). */
	componentHeight?: number;
	/** Starting X position (default: 50). */
	startX?: number;
	/** Starting Y position (default: 200). */
	startY?: number;
}

const DEFAULT_OPTIONS: Required<LayoutOptions> = {
	horizontalSpacing: 120,
	verticalSpacing: 100,
	componentWidth: 60,
	componentHeight: 40,
	startX: 50,
	startY: 200
};

// ============================================================================
// Layout Algorithm
// ============================================================================

/**
 * Build an adjacency list from connections.
 */
function buildAdjacencyList(
	components: Component[],
	connections: PipeConnection[]
): Map<string, string[]> {
	const adjacency = new Map<string, string[]>();

	// Initialize all components with empty adjacency lists
	for (const comp of components) {
		adjacency.set(comp.id, []);
	}

	// Add connections
	for (const conn of connections) {
		const neighbors = adjacency.get(conn.from_component_id);
		if (neighbors) {
			neighbors.push(conn.to_component_id);
		}
	}

	return adjacency;
}

/**
 * Find root components (components with no incoming connections).
 */
function findRoots(
	components: Component[],
	connections: PipeConnection[]
): string[] {
	const hasIncoming = new Set<string>();

	for (const conn of connections) {
		hasIncoming.add(conn.to_component_id);
	}

	return components
		.filter((comp) => !hasIncoming.has(comp.id))
		.map((comp) => comp.id);
}

/**
 * Assign levels to components using BFS (topological-like ordering).
 * Level 0 = root components, Level 1 = their children, etc.
 */
function assignLevels(
	roots: string[],
	adjacency: Map<string, string[]>
): Map<string, number> {
	const levels = new Map<string, number>();
	const queue: Array<{ id: string; level: number }> = [];

	// Start with roots at level 0
	for (const root of roots) {
		queue.push({ id: root, level: 0 });
		levels.set(root, 0);
	}

	// BFS to assign levels
	while (queue.length > 0) {
		const { id, level } = queue.shift()!;
		const neighbors = adjacency.get(id) || [];

		for (const neighbor of neighbors) {
			// Only process if not visited or found a longer path
			const existingLevel = levels.get(neighbor);
			if (existingLevel === undefined || existingLevel < level + 1) {
				levels.set(neighbor, level + 1);
				queue.push({ id: neighbor, level: level + 1 });
			}
		}
	}

	return levels;
}

/**
 * Group components by their level.
 */
function groupByLevel(levels: Map<string, number>): Map<number, string[]> {
	const groups = new Map<number, string[]>();

	for (const [id, level] of levels) {
		if (!groups.has(level)) {
			groups.set(level, []);
		}
		groups.get(level)!.push(id);
	}

	return groups;
}

/**
 * Calculate positions for all components.
 */
function calculatePositions(
	components: Component[],
	levelGroups: Map<number, string[]>,
	options: Required<LayoutOptions>
): Map<string, ComponentPosition> {
	const positions = new Map<string, ComponentPosition>();

	// Sort levels
	const sortedLevels = Array.from(levelGroups.keys()).sort((a, b) => a - b);

	for (const level of sortedLevels) {
		const ids = levelGroups.get(level)!;
		const x = options.startX + level * (options.componentWidth + options.horizontalSpacing);

		// Center components vertically at this level
		const totalHeight = ids.length * options.componentHeight + (ids.length - 1) * options.verticalSpacing;
		const startY = options.startY - totalHeight / 2;

		for (let i = 0; i < ids.length; i++) {
			const id = ids[i];
			const y = startY + i * (options.componentHeight + options.verticalSpacing);

			positions.set(id, {
				id,
				x,
				y,
				width: options.componentWidth,
				height: options.componentHeight
			});
		}
	}

	return positions;
}

/**
 * Generate connection lines between positioned components.
 */
function generateConnectionLines(
	connections: PipeConnection[],
	positions: Map<string, ComponentPosition>,
	options: Required<LayoutOptions>
): ConnectionLine[] {
	const lines: ConnectionLine[] = [];

	for (const conn of connections) {
		const fromPos = positions.get(conn.from_component_id);
		const toPos = positions.get(conn.to_component_id);

		if (!fromPos || !toPos) continue;

		// Calculate connection points (right edge of from, left edge of to)
		const fromX = fromPos.x + fromPos.width;
		const fromY = fromPos.y + fromPos.height / 2;
		const toX = toPos.x;
		const toY = toPos.y + toPos.height / 2;

		// Create a simple orthogonal path
		const midX = (fromX + toX) / 2;

		lines.push({
			id: conn.id,
			fromId: conn.from_component_id,
			toId: conn.to_component_id,
			fromPort: conn.from_port_id,
			toPort: conn.to_port_id,
			points: [
				{ x: fromX, y: fromY },
				{ x: midX, y: fromY },
				{ x: midX, y: toY },
				{ x: toX, y: toY }
			]
		});
	}

	return lines;
}

/**
 * Calculate the bounding box of all positioned components.
 */
function calculateBounds(positions: Map<string, ComponentPosition>): LayoutResult['bounds'] {
	if (positions.size === 0) {
		return { x: 0, y: 0, width: 100, height: 100 };
	}

	let minX = Infinity;
	let minY = Infinity;
	let maxX = -Infinity;
	let maxY = -Infinity;

	for (const pos of positions.values()) {
		minX = Math.min(minX, pos.x);
		minY = Math.min(minY, pos.y);
		maxX = Math.max(maxX, pos.x + pos.width);
		maxY = Math.max(maxY, pos.y + pos.height);
	}

	// Add padding
	const padding = 50;
	return {
		x: minX - padding,
		y: minY - padding,
		width: maxX - minX + padding * 2,
		height: maxY - minY + padding * 2
	};
}

// ============================================================================
// Public API
// ============================================================================

/**
 * Calculate layout for a hydraulic network.
 *
 * This algorithm:
 * 1. Builds a graph from components and connections
 * 2. Finds root nodes (typically reservoirs/tanks)
 * 3. Assigns levels using BFS traversal
 * 4. Positions components left-to-right by level
 * 5. Generates orthogonal connection lines
 *
 * @param components - Array of network components
 * @param connections - Array of connections between components
 * @param options - Layout options
 * @returns Layout result with positioned components and connection lines
 */
export function calculateLayout(
	components: Component[],
	connections: PipeConnection[],
	options: LayoutOptions = {}
): LayoutResult {
	const opts = { ...DEFAULT_OPTIONS, ...options };

	// Handle empty network
	if (components.length === 0) {
		return {
			components: [],
			connections: [],
			bounds: { x: 0, y: 0, width: 100, height: 100 }
		};
	}

	// Build graph structure
	const adjacency = buildAdjacencyList(components, connections);
	const roots = findRoots(components, connections);

	// Handle networks with no clear root (cycles)
	const effectiveRoots = roots.length > 0 ? roots : [components[0].id];

	// Assign levels
	const levels = assignLevels(effectiveRoots, adjacency);

	// Handle disconnected components (not reachable from roots)
	let maxLevel = 0;
	for (const level of levels.values()) {
		maxLevel = Math.max(maxLevel, level);
	}
	for (const comp of components) {
		if (!levels.has(comp.id)) {
			levels.set(comp.id, maxLevel + 1);
		}
	}

	// Group by level and calculate positions
	const levelGroups = groupByLevel(levels);
	const positions = calculatePositions(components, levelGroups, opts);

	// Generate connection lines
	const connectionLines = generateConnectionLines(connections, positions, opts);

	// Calculate bounds
	const bounds = calculateBounds(positions);

	return {
		components: Array.from(positions.values()),
		connections: connectionLines,
		bounds
	};
}

/**
 * Apply manual position override to a layout result.
 *
 * @param layout - Original layout result
 * @param overrides - Map of component ID to position override
 * @returns New layout result with overrides applied
 */
export function applyPositionOverrides(
	layout: LayoutResult,
	overrides: Map<string, { x: number; y: number }>
): LayoutResult {
	const newComponents = layout.components.map((comp) => {
		const override = overrides.get(comp.id);
		if (override) {
			return { ...comp, x: override.x, y: override.y };
		}
		return comp;
	});

	// Rebuild connection lines with new positions
	const positions = new Map<string, ComponentPosition>();
	for (const comp of newComponents) {
		positions.set(comp.id, comp);
	}

	// Re-generate connection lines
	const connections = layout.connections.map((conn) => {
		const fromPos = positions.get(conn.fromId);
		const toPos = positions.get(conn.toId);

		if (!fromPos || !toPos) return conn;

		const fromX = fromPos.x + fromPos.width;
		const fromY = fromPos.y + fromPos.height / 2;
		const toX = toPos.x;
		const toY = toPos.y + toPos.height / 2;
		const midX = (fromX + toX) / 2;

		return {
			...conn,
			points: [
				{ x: fromX, y: fromY },
				{ x: midX, y: fromY },
				{ x: midX, y: toY },
				{ x: toX, y: toY }
			]
		};
	});

	// Recalculate bounds
	const bounds = calculateBounds(positions);

	return {
		components: newComponents,
		connections,
		bounds
	};
}
