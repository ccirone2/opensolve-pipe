/**
 * Tests for pump model functions.
 */

import { describe, it, expect } from 'vitest';
import {
	validatePumpCurve,
	createDefaultPumpCurve,
	interpolatePumpHead,
	interpolateEfficiency,
	fitQuadratic,
	evaluateQuadratic,
	findQuadraticMaximum,
	generateEfficiencyBestFitCurve,
	generatePumpBestFitCurve,
	calculateBEP
} from '../pump';
import type { PumpCurve } from '../pump';

describe('validatePumpCurve', () => {
	it('should reject curves with less than 2 points', () => {
		const curve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [{ flow: 0, head: 100 }]
		};
		expect(validatePumpCurve(curve)).toBe('Pump curve must have at least 2 points');
	});

	it('should reject unsorted points', () => {
		const curve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [
				{ flow: 100, head: 50 },
				{ flow: 50, head: 75 }
			]
		};
		expect(validatePumpCurve(curve)).toBe('Pump curve points must be sorted by ascending flow');
	});

	it('should reject negative flow values', () => {
		const curve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [
				{ flow: -10, head: 100 },
				{ flow: 50, head: 75 }
			]
		};
		expect(validatePumpCurve(curve)).toBe('Flow values cannot be negative');
	});

	it('should reject invalid efficiency values', () => {
		const curve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [
				{ flow: 0, head: 100 },
				{ flow: 50, head: 75 }
			],
			efficiency_curve: [{ flow: 25, efficiency: 1.5 }]
		};
		expect(validatePumpCurve(curve)).toBe('Efficiency values must be between 0 and 1');
	});

	it('should accept valid curves', () => {
		const curve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [
				{ flow: 0, head: 100 },
				{ flow: 50, head: 75 },
				{ flow: 100, head: 50 }
			]
		};
		expect(validatePumpCurve(curve)).toBeNull();
	});
});

describe('createDefaultPumpCurve', () => {
	it('should create a valid curve with 5 points', () => {
		const curve = createDefaultPumpCurve('test-id');
		expect(curve.id).toBe('test-id');
		expect(curve.points.length).toBe(5);
		expect(validatePumpCurve(curve)).toBeNull();
	});
});

describe('interpolatePumpHead', () => {
	const curve: PumpCurve = {
		id: 'test',
		name: 'Test',
		points: [
			{ flow: 0, head: 100 },
			{ flow: 100, head: 80 },
			{ flow: 200, head: 50 }
		]
	};

	it('should return null for curves with less than 2 points', () => {
		const smallCurve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [{ flow: 0, head: 100 }]
		};
		expect(interpolatePumpHead(smallCurve, 50)).toBeNull();
	});

	it('should return first point head for flow below range', () => {
		expect(interpolatePumpHead(curve, -10)).toBe(100);
	});

	it('should return last point head for flow above range', () => {
		expect(interpolatePumpHead(curve, 300)).toBe(50);
	});

	it('should interpolate head at midpoint', () => {
		expect(interpolatePumpHead(curve, 50)).toBe(90);
	});

	it('should interpolate head between second and third points', () => {
		expect(interpolatePumpHead(curve, 150)).toBe(65);
	});
});

describe('interpolateEfficiency', () => {
	const curveWithEfficiency: PumpCurve = {
		id: 'test',
		name: 'Test',
		points: [
			{ flow: 0, head: 100 },
			{ flow: 100, head: 80 },
			{ flow: 200, head: 50 }
		],
		efficiency_curve: [
			{ flow: 0, efficiency: 0 },
			{ flow: 100, efficiency: 0.8 },
			{ flow: 200, efficiency: 0.6 }
		]
	};

	it('should return null for curves without efficiency data', () => {
		const curve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [
				{ flow: 0, head: 100 },
				{ flow: 100, head: 80 }
			]
		};
		expect(interpolateEfficiency(curve, 50)).toBeNull();
	});

	it('should return null for efficiency curves with less than 2 points', () => {
		const curve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [
				{ flow: 0, head: 100 },
				{ flow: 100, head: 80 }
			],
			efficiency_curve: [{ flow: 50, efficiency: 0.7 }]
		};
		expect(interpolateEfficiency(curve, 50)).toBeNull();
	});

	it('should return first point efficiency for flow below range', () => {
		expect(interpolateEfficiency(curveWithEfficiency, -10)).toBe(0);
	});

	it('should return last point efficiency for flow above range', () => {
		expect(interpolateEfficiency(curveWithEfficiency, 300)).toBe(0.6);
	});

	it('should interpolate efficiency at midpoint', () => {
		expect(interpolateEfficiency(curveWithEfficiency, 50)).toBe(0.4);
	});

	it('should interpolate efficiency between second and third points', () => {
		expect(interpolateEfficiency(curveWithEfficiency, 150)).toBe(0.7);
	});
});

describe('fitQuadratic', () => {
	it('should return null for fewer than 3 points', () => {
		const points = [
			{ x: 0, y: 0 },
			{ x: 1, y: 1 }
		];
		expect(fitQuadratic(points)).toBeNull();
	});

	it('should fit a perfect parabola', () => {
		// y = x^2 (a=1, b=0, c=0)
		const points = [
			{ x: -2, y: 4 },
			{ x: -1, y: 1 },
			{ x: 0, y: 0 },
			{ x: 1, y: 1 },
			{ x: 2, y: 4 }
		];
		const coeffs = fitQuadratic(points);
		expect(coeffs).not.toBeNull();
		expect(coeffs!.a).toBeCloseTo(1, 5);
		expect(coeffs!.b).toBeCloseTo(0, 5);
		expect(coeffs!.c).toBeCloseTo(0, 5);
	});

	it('should fit a downward parabola', () => {
		// y = -0.5x^2 + 2x + 1 (typical efficiency curve shape)
		const points = [
			{ x: 0, y: 1 },
			{ x: 1, y: 2.5 },
			{ x: 2, y: 3 },
			{ x: 3, y: 2.5 },
			{ x: 4, y: 1 }
		];
		const coeffs = fitQuadratic(points);
		expect(coeffs).not.toBeNull();
		expect(coeffs!.a).toBeCloseTo(-0.5, 5);
		expect(coeffs!.b).toBeCloseTo(2, 5);
		expect(coeffs!.c).toBeCloseTo(1, 5);
	});
});

describe('evaluateQuadratic', () => {
	it('should evaluate quadratic at given x', () => {
		const coeffs = { a: 1, b: -2, c: 1 }; // (x-1)^2 = x^2 - 2x + 1
		expect(evaluateQuadratic(coeffs, 0)).toBe(1);
		expect(evaluateQuadratic(coeffs, 1)).toBe(0);
		expect(evaluateQuadratic(coeffs, 2)).toBe(1);
		expect(evaluateQuadratic(coeffs, 3)).toBe(4);
	});
});

describe('findQuadraticMaximum', () => {
	it('should return null for upward-opening parabola', () => {
		const coeffs = { a: 1, b: 0, c: 0 }; // y = x^2
		expect(findQuadraticMaximum(coeffs)).toBeNull();
	});

	it('should find maximum of downward-opening parabola', () => {
		// y = -x^2 + 4x - 3 = -(x-2)^2 + 1, max at x=2, y=1
		const coeffs = { a: -1, b: 4, c: -3 };
		const max = findQuadraticMaximum(coeffs);
		expect(max).not.toBeNull();
		expect(max!.x).toBeCloseTo(2, 5);
		expect(max!.y).toBeCloseTo(1, 5);
	});

	it('should find maximum of typical efficiency curve shape', () => {
		// y = -0.00005x^2 + 0.01x + 0.2 (max around x=100)
		const coeffs = { a: -0.00005, b: 0.01, c: 0.2 };
		const max = findQuadraticMaximum(coeffs);
		expect(max).not.toBeNull();
		expect(max!.x).toBeCloseTo(100, 1);
	});
});

describe('generateEfficiencyBestFitCurve', () => {
	it('should return null for curves without efficiency data', () => {
		const curve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [
				{ flow: 0, head: 100 },
				{ flow: 100, head: 80 }
			]
		};
		expect(generateEfficiencyBestFitCurve(curve)).toBeNull();
	});

	it('should return null for fewer than 3 efficiency points', () => {
		const curve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [
				{ flow: 0, head: 100 },
				{ flow: 100, head: 80 }
			],
			efficiency_curve: [
				{ flow: 0, efficiency: 0 },
				{ flow: 100, efficiency: 0.8 }
			]
		};
		expect(generateEfficiencyBestFitCurve(curve)).toBeNull();
	});

	it('should generate smooth curve from efficiency data', () => {
		const curve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [
				{ flow: 0, head: 100 },
				{ flow: 100, head: 80 },
				{ flow: 200, head: 50 }
			],
			efficiency_curve: [
				{ flow: 0, efficiency: 0 },
				{ flow: 50, efficiency: 0.6 },
				{ flow: 100, efficiency: 0.8 },
				{ flow: 150, efficiency: 0.75 },
				{ flow: 200, efficiency: 0.5 }
			]
		};

		const result = generateEfficiencyBestFitCurve(curve, 10);
		expect(result).not.toBeNull();
		expect(result!.length).toBe(10);

		// Check flow range
		expect(result![0].flow).toBe(0);
		expect(result![result!.length - 1].flow).toBe(200);

		// All efficiency values should be valid (0-1)
		for (const point of result!) {
			expect(point.efficiency).toBeGreaterThanOrEqual(0);
			expect(point.efficiency).toBeLessThanOrEqual(1);
		}
	});

	it('should clamp efficiency values to valid range', () => {
		// Extreme data that might produce out-of-range predictions
		const curve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [
				{ flow: 0, head: 100 },
				{ flow: 100, head: 50 }
			],
			efficiency_curve: [
				{ flow: 0, efficiency: 0.1 },
				{ flow: 50, efficiency: 0.9 },
				{ flow: 100, efficiency: 0.1 }
			]
		};

		const result = generateEfficiencyBestFitCurve(curve);
		expect(result).not.toBeNull();

		// All values should be clamped to 0-1
		for (const point of result!) {
			expect(point.efficiency).toBeGreaterThanOrEqual(0);
			expect(point.efficiency).toBeLessThanOrEqual(1);
		}
	});
});

describe('generatePumpBestFitCurve', () => {
	it('should return null for fewer than 3 points', () => {
		const curve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [
				{ flow: 0, head: 100 },
				{ flow: 100, head: 80 }
			]
		};
		expect(generatePumpBestFitCurve(curve)).toBeNull();
	});

	it('should generate smooth curve from pump data', () => {
		const curve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [
				{ flow: 0, head: 100 },
				{ flow: 50, head: 95 },
				{ flow: 100, head: 85 },
				{ flow: 150, head: 70 },
				{ flow: 200, head: 50 }
			]
		};

		const result = generatePumpBestFitCurve(curve, 10);
		expect(result).not.toBeNull();
		expect(result!.length).toBe(10);

		// Check flow range
		expect(result![0].flow).toBe(0);
		expect(result![result!.length - 1].flow).toBe(200);

		// Pump curve should be decreasing (typical shape)
		expect(result![0].head).toBeGreaterThan(result![result!.length - 1].head);
	});
});

describe('calculateBEP', () => {
	it('should return null for curves without efficiency data', () => {
		const curve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [
				{ flow: 0, head: 100 },
				{ flow: 100, head: 80 }
			]
		};
		expect(calculateBEP(curve)).toBeNull();
	});

	it('should find BEP using quadratic fit maximum', () => {
		// Symmetric efficiency curve with clear peak at flow=100
		const curve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [
				{ flow: 0, head: 120 },
				{ flow: 50, head: 110 },
				{ flow: 100, head: 95 },
				{ flow: 150, head: 75 },
				{ flow: 200, head: 50 }
			],
			efficiency_curve: [
				{ flow: 0, efficiency: 0 },
				{ flow: 50, efficiency: 0.55 },
				{ flow: 100, efficiency: 0.80 },
				{ flow: 150, efficiency: 0.55 },
				{ flow: 200, efficiency: 0 }
			]
		};

		const bep = calculateBEP(curve);
		expect(bep).not.toBeNull();
		// BEP should be at flow=100 (symmetric efficiency curve peaks there)
		expect(bep!.flow).toBeCloseTo(100, 0);
		// Efficiency at peak should be around 0.8
		expect(bep!.efficiency).toBeCloseTo(0.8, 1);
		// Head from pump curve fit at BEP flow
		expect(bep!.head).toBeGreaterThan(70);
		expect(bep!.head).toBeLessThan(110);
	});

	it('should fall back to raw data for fewer than 3 efficiency points', () => {
		const curve: PumpCurve = {
			id: 'test',
			name: 'Test',
			points: [
				{ flow: 0, head: 100 },
				{ flow: 100, head: 80 }
			],
			efficiency_curve: [
				{ flow: 50, efficiency: 0.7 },
				{ flow: 100, efficiency: 0.8 }
			]
		};

		const bep = calculateBEP(curve);
		expect(bep).not.toBeNull();
		// Should use raw data maximum
		expect(bep!.flow).toBe(100);
		expect(bep!.efficiency).toBe(0.8);
	});
});
