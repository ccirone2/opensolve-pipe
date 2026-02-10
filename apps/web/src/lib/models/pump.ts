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

/** A single point on a power curve (flow vs brake horsepower). */
export interface FlowPowerPoint {
	/** Flow rate in project units. */
	flow: number;
	/** Power (BHP) in project units. */
	power: number;
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
	/** Number of pump stages. */
	stages?: number;
	/** Inlet/outlet size description (e.g. "2\" / 2\""). */
	inlet_outlet?: string;
	/** Free-form notes. */
	notes?: string;
	/** Pump curve points (minimum 2). */
	points: FlowHeadPoint[];
	/** Optional efficiency curve. */
	efficiency_curve?: FlowEfficiencyPoint[];
	/** Optional NPSH required curve. */
	npshr_curve?: NPSHRPoint[];
	/** Optional power curve. */
	power_curve?: FlowPowerPoint[];
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

/** Quadratic regression coefficients (a, b, c) for y = ax² + bx + c */
export interface QuadraticCoefficients {
	a: number;
	b: number;
	c: number;
}

/**
 * Fit a quadratic curve (y = ax² + bx + c) to data points using least squares regression.
 * Returns null if there are fewer than 3 points.
 */
export function fitQuadratic(
	points: { x: number; y: number }[]
): QuadraticCoefficients | null {
	if (points.length < 3) return null;

	const n = points.length;

	// Calculate sums for normal equations
	let sumX = 0,
		sumX2 = 0,
		sumX3 = 0,
		sumX4 = 0;
	let sumY = 0,
		sumXY = 0,
		sumX2Y = 0;

	for (const p of points) {
		const x = p.x;
		const y = p.y;
		const x2 = x * x;
		const x3 = x2 * x;
		const x4 = x3 * x;

		sumX += x;
		sumX2 += x2;
		sumX3 += x3;
		sumX4 += x4;
		sumY += y;
		sumXY += x * y;
		sumX2Y += x2 * y;
	}

	// Solve the system of normal equations using Cramer's rule
	// [n,    sumX,  sumX2 ] [c]   [sumY  ]
	// [sumX, sumX2, sumX3 ] [b] = [sumXY ]
	// [sumX2,sumX3, sumX4 ] [a]   [sumX2Y]

	const det =
		n * (sumX2 * sumX4 - sumX3 * sumX3) -
		sumX * (sumX * sumX4 - sumX3 * sumX2) +
		sumX2 * (sumX * sumX3 - sumX2 * sumX2);

	if (Math.abs(det) < 1e-10) return null;

	const detA =
		sumY * (sumX2 * sumX4 - sumX3 * sumX3) -
		sumX * (sumXY * sumX4 - sumX3 * sumX2Y) +
		sumX2 * (sumXY * sumX3 - sumX2 * sumX2Y);

	const detB =
		n * (sumXY * sumX4 - sumX3 * sumX2Y) -
		sumY * (sumX * sumX4 - sumX3 * sumX2) +
		sumX2 * (sumX * sumX2Y - sumXY * sumX2);

	const detC =
		n * (sumX2 * sumX2Y - sumXY * sumX3) -
		sumX * (sumX * sumX2Y - sumXY * sumX2) +
		sumY * (sumX * sumX3 - sumX2 * sumX2);

	return {
		a: detC / det,
		b: detB / det,
		c: detA / det
	};
}

/**
 * Evaluate a quadratic function at a given x value.
 */
export function evaluateQuadratic(coeffs: QuadraticCoefficients, x: number): number {
	return coeffs.a * x * x + coeffs.b * x + coeffs.c;
}

/**
 * Generate a smooth quadratic best-fit curve from efficiency data points.
 * Returns an array of points for plotting, or null if fitting fails.
 */
export function generateEfficiencyBestFitCurve(
	curve: PumpCurve,
	numPoints: number = 50
): { flow: number; efficiency: number }[] | null {
	if (!curve.efficiency_curve || curve.efficiency_curve.length < 3) return null;

	// Convert to x,y format for fitting
	const dataPoints = curve.efficiency_curve.map((p) => ({ x: p.flow, y: p.efficiency }));

	// Fit quadratic
	const coeffs = fitQuadratic(dataPoints);
	if (!coeffs) return null;

	// Get flow range
	const flows = curve.efficiency_curve.map((p) => p.flow);
	const minFlow = Math.min(...flows);
	const maxFlow = Math.max(...flows);

	// Generate smooth curve points
	const result: { flow: number; efficiency: number }[] = [];
	for (let i = 0; i < numPoints; i++) {
		const flow = minFlow + (i / (numPoints - 1)) * (maxFlow - minFlow);
		let efficiency = evaluateQuadratic(coeffs, flow);
		// Clamp efficiency to valid range
		efficiency = Math.max(0, Math.min(1, efficiency));
		result.push({ flow, efficiency });
	}

	return result;
}

/**
 * Generate a smooth quadratic best-fit curve from pump head data points.
 * Returns an array of points for plotting, or null if fitting fails.
 */
export function generatePumpBestFitCurve(
	curve: PumpCurve,
	numPoints: number = 50
): { flow: number; head: number }[] | null {
	if (!curve.points || curve.points.length < 3) return null;

	// Convert to x,y format for fitting
	const dataPoints = curve.points.map((p) => ({ x: p.flow, y: p.head }));

	// Fit quadratic
	const coeffs = fitQuadratic(dataPoints);
	if (!coeffs) return null;

	// Get flow range
	const flows = curve.points.map((p) => p.flow);
	const minFlow = Math.min(...flows);
	const maxFlow = Math.max(...flows);

	// Generate smooth curve points
	const result: { flow: number; head: number }[] = [];
	for (let i = 0; i < numPoints; i++) {
		const flow = minFlow + (i / (numPoints - 1)) * (maxFlow - minFlow);
		const head = evaluateQuadratic(coeffs, flow);
		result.push({ flow, head });
	}

	return result;
}

/**
 * Find the x value where a quadratic function reaches its maximum (vertex).
 * For y = ax² + bx + c, the vertex is at x = -b/(2a).
 * Returns null if a >= 0 (parabola opens upward, no maximum).
 */
export function findQuadraticMaximum(coeffs: QuadraticCoefficients): { x: number; y: number } | null {
	// For a maximum, we need a < 0 (parabola opens downward)
	if (coeffs.a >= 0) return null;

	const x = -coeffs.b / (2 * coeffs.a);
	const y = evaluateQuadratic(coeffs, x);

	return { x, y };
}

/**
 * Get the quadratic coefficients for the pump head curve.
 */
export function getPumpCurveCoefficients(curve: PumpCurve): QuadraticCoefficients | null {
	if (!curve.points || curve.points.length < 3) return null;
	const dataPoints = curve.points.map((p) => ({ x: p.flow, y: p.head }));
	return fitQuadratic(dataPoints);
}

/**
 * Get the quadratic coefficients for the efficiency curve.
 */
export function getEfficiencyCurveCoefficients(curve: PumpCurve): QuadraticCoefficients | null {
	if (!curve.efficiency_curve || curve.efficiency_curve.length < 3) return null;
	const dataPoints = curve.efficiency_curve.map((p) => ({ x: p.flow, y: p.efficiency }));
	return fitQuadratic(dataPoints);
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
 * Uses quadratic best-fit to find the true maximum efficiency point.
 * Falls back to raw data maximum if quadratic fit fails.
 * Returns null if no efficiency curve data is provided.
 */
export function calculateBEP(curve: PumpCurve): BestEfficiencyPoint | null {
	if (!curve.efficiency_curve || curve.efficiency_curve.length === 0) {
		return null;
	}

	// Try quadratic fit first (requires 3+ points)
	const effCoeffs = getEfficiencyCurveCoefficients(curve);
	const pumpCoeffs = getPumpCurveCoefficients(curve);

	if (effCoeffs && pumpCoeffs) {
		// Find the mathematical maximum of the efficiency curve
		const maxPoint = findQuadraticMaximum(effCoeffs);

		if (maxPoint) {
			// Ensure the max is within the data range
			const flows = curve.efficiency_curve.map((p) => p.flow);
			const minFlow = Math.min(...flows);
			const maxFlow = Math.max(...flows);

			if (maxPoint.x >= minFlow && maxPoint.x <= maxFlow) {
				// Get head from pump curve fit at BEP flow
				const head = evaluateQuadratic(pumpCoeffs, maxPoint.x);
				// Clamp efficiency to valid range
				const efficiency = Math.max(0, Math.min(1, maxPoint.y));

				return {
					flow: maxPoint.x,
					efficiency,
					head
				};
			}
		}
	}

	// Fallback: Find the point with maximum efficiency from raw data
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
