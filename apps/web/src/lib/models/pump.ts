/**
 * Pump curve and pump-related models.
 * Mirrors: apps/api/src/opensolve_pipe/models/pump.py
 */

/** A single point on a pump curve (flow vs head). */
export interface FlowHeadPoint {
	/** Flow rate in project units. */
	flow: number;
	/** Head in project units. */
	head: number;
}

/** A single point on an efficiency curve (flow vs efficiency). */
export interface FlowEfficiencyPoint {
	/** Flow rate in project units. */
	flow: number;
	/** Pump efficiency as fraction (0-1). */
	efficiency: number;
}

/** A single point on NPSH required curve. */
export interface NPSHRPoint {
	/** Flow rate in project units. */
	flow: number;
	/** NPSH required in project units. */
	npsh_required: number;
}

/** Pump performance curve definition. */
export interface PumpCurve {
	/** Unique identifier for this pump curve. */
	id: string;
	/** Display name for this pump curve. */
	name: string;
	/** Pump manufacturer. */
	manufacturer?: string;
	/** Pump model number. */
	model?: string;
	/** Rated speed in RPM. */
	rated_speed?: number;
	/** Impeller diameter in project units. */
	impeller_diameter?: number;
	/** Pump curve points (minimum 2). */
	points: FlowHeadPoint[];
	/** Optional efficiency curve. */
	efficiency_curve?: FlowEfficiencyPoint[];
	/** Optional NPSH required curve. */
	npshr_curve?: NPSHRPoint[];
}

/** Validate pump curve. Returns error message or null if valid. */
export function validatePumpCurve(curve: PumpCurve): string | null {
	if (curve.points.length < 2) {
		return 'Pump curve must have at least 2 points';
	}

	// Check if points are sorted by flow
	for (let i = 1; i < curve.points.length; i++) {
		if (curve.points[i].flow < curve.points[i - 1].flow) {
			return 'Pump curve points must be sorted by ascending flow';
		}
	}

	// Check for negative values
	for (const point of curve.points) {
		if (point.flow < 0) {
			return 'Flow values cannot be negative';
		}
		if (point.head < 0) {
			return 'Head values cannot be negative';
		}
	}

	// Validate efficiency curve if present
	if (curve.efficiency_curve) {
		for (const point of curve.efficiency_curve) {
			if (point.efficiency < 0 || point.efficiency > 1) {
				return 'Efficiency values must be between 0 and 1';
			}
		}
	}

	return null;
}

/** Create a default pump curve with sample points. */
export function createDefaultPumpCurve(id: string): PumpCurve {
	return {
		id,
		name: 'New Pump Curve',
		points: [
			{ flow: 0, head: 100 },
			{ flow: 50, head: 95 },
			{ flow: 100, head: 85 },
			{ flow: 150, head: 70 },
			{ flow: 200, head: 50 }
		]
	};
}

/** Interpolate head at a given flow using the pump curve. */
export function interpolatePumpHead(curve: PumpCurve, flow: number): number | null {
	if (curve.points.length < 2) return null;

	const points = curve.points;

	// Handle flow outside curve range
	if (flow <= points[0].flow) return points[0].head;
	if (flow >= points[points.length - 1].flow) return points[points.length - 1].head;

	// Find surrounding points and interpolate
	for (let i = 1; i < points.length; i++) {
		if (flow <= points[i].flow) {
			const p0 = points[i - 1];
			const p1 = points[i];
			const t = (flow - p0.flow) / (p1.flow - p0.flow);
			return p0.head + t * (p1.head - p0.head);
		}
	}

	return null;
}

/** Interpolate efficiency at a given flow using the efficiency curve. */
export function interpolateEfficiency(curve: PumpCurve, flow: number): number | null {
	if (!curve.efficiency_curve || curve.efficiency_curve.length < 2) return null;

	const points = curve.efficiency_curve;

	// Handle flow outside curve range
	if (flow <= points[0].flow) return points[0].efficiency;
	if (flow >= points[points.length - 1].flow) return points[points.length - 1].efficiency;

	// Find surrounding points and interpolate
	for (let i = 1; i < points.length; i++) {
		if (flow <= points[i].flow) {
			const p0 = points[i - 1];
			const p1 = points[i];
			const t = (flow - p0.flow) / (p1.flow - p0.flow);
			return p0.efficiency + t * (p1.efficiency - p0.efficiency);
		}
	}

	return null;
}

/** Best Efficiency Point (BEP) data. */
export interface BestEfficiencyPoint {
	/** Flow rate at BEP. */
	flow: number;
	/** Efficiency at BEP (0-1). */
	efficiency: number;
	/** Head at BEP (interpolated from pump curve). */
	head: number;
}

/**
 * Calculate the Best Efficiency Point (BEP) from efficiency curve data.
 * Returns null if no efficiency curve data is provided.
 */
export function calculateBEP(curve: PumpCurve): BestEfficiencyPoint | null {
	if (!curve.efficiency_curve || curve.efficiency_curve.length === 0) {
		return null;
	}

	// Find the point with maximum efficiency
	let maxEfficiencyPoint = curve.efficiency_curve[0];
	for (const point of curve.efficiency_curve) {
		if (point.efficiency > maxEfficiencyPoint.efficiency) {
			maxEfficiencyPoint = point;
		}
	}

	// Interpolate the head at BEP flow from the pump curve
	const head = interpolatePumpHead(curve, maxEfficiencyPoint.flow);
	if (head === null) {
		return null;
	}

	return {
		flow: maxEfficiencyPoint.flow,
		efficiency: maxEfficiencyPoint.efficiency,
		head
	};
}
